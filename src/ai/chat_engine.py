"""
chat_engine.py
--------------
AI-powered chat engine using DeepSeek (or any OpenAI-compatible LLM).

Flow
----
  User question
      │
      ▼  Step 1 — Router
  Is this a data question or a concept question?
      │                        │
      ▼                        ▼
  Step 2 — SQL Gen        Direct answer
  LLM writes DuckDB SQL
      │
      ▼  Step 3 — Execute
  DuckDB runs the SQL → DataFrame
      │
      ▼  Step 4 — Answer
  LLM formats the result in plain English + markdown table hint

The LLM has access to the DuckDB schema (ohlcv + signals tables) and
a snapshot of today's market summary as context.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import pandas as pd

from src.ai.llm.client import LLMClient
from src.database.duckdb_store import get_store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema description injected into every prompt
# ---------------------------------------------------------------------------

DB_SCHEMA = """
You have access to a DuckDB database with three tables:

TABLE: ohlcv
  symbol   TEXT     -- NSE symbol
  date     DATE     -- trading date
  open, high, low, close  DOUBLE   -- prices in INR
  volume   BIGINT

TABLE: signals   (one row per stock, latest session, Python-scored)
  symbol              TEXT
  sector              TEXT     -- e.g. 'IT', 'Banking', 'Defence', 'Other'
  last_close          DOUBLE
  pct_1d              DOUBLE   -- 1-session % change
  pct_5d              DOUBLE   -- 5-session % change
  pct_20d             DOUBLE   -- 20-session % change
  volume_ratio        DOUBLE   -- today vol / 20d avg vol
  volume_spike        BOOLEAN  -- volume_ratio >= 2
  breakout            BOOLEAN  -- close > prior 20d high
  above_50dma         BOOLEAN  -- price > 50-day MA
  near_52w_high       BOOLEAN  -- within 5% of 52-week high
  big_mover           BOOLEAN  -- |pct_1d| >= 8%
  rsi_14              DOUBLE   -- RSI (14-period)
  green_days_5        INTEGER  -- green candles in last 5 sessions
  gap_pct             DOUBLE   -- today's gap % vs prior close
  breakout_age        INTEGER  -- 0=today, 1=yesterday, 2=2d ago, 99=no recent breakout
  pct_above_50dma     DOUBLE   -- % above/below 50-day MA (negative = below)
  pct_from_52w_high   DOUBLE   -- % below 52-week high
  range_position      DOUBLE   -- position in 52w range (0=low, 100=high)
  atr_pct             DOUBLE   -- 5-day avg true range as % of price (volatility)

  -- 4 Python-computed scores (0-100 each):
  momentum_score      DOUBLE   -- current trend strength (high = strong)
                               --   typical range: 0-78. p75=34, p90=44, max=78
  continuation_prob   DOUBLE   -- empirical prob of >=4% gain next 5 sessions
                               --   typical range: 0-60. p75=18, anything >25 is high
  exhaustion_score    DOUBLE   -- overextension risk (high = likely to reverse)
                               --   typical range: 0-100. p75=12; >30 means overextended
  risk_score          DOUBLE   -- downside risk: liquidity, volatility, gap risk
                               --   typical range: 0-68. p25=20; <25 means low risk
  reward_risk_ratio   DOUBLE   -- continuation_prob / downside_prob (higher = better)
  final_score         DOUBLE   -- composite 0-100 ranking score
  trade_category      TEXT     -- 'High Conviction' / 'Momentum' / 'Early Breakout' /
                               --   'Pullback Candidate' / 'High Risk / High Reward' / 'Watchlist'
  asset_type          TEXT     -- always 'Equity' (ETFs are excluded from this table)

IMPORTANT THRESHOLDS (use these, not guesses):
  High momentum:      momentum_score >= 40    (top 25%)
  Very high momentum: momentum_score >= 50    (top 10%)
  High cont. prob:    continuation_prob >= 25
  Low exhaustion:     exhaustion_score <= 20
  Low risk:           risk_score <= 30
  Fresh breakout:     breakout_age <= 2       (0=today, 1=yesterday, 2=2d ago)
  Volume spike:       volume_ratio >= 2

TABLE: sector_map
  symbol TEXT
  sector TEXT

Use signals for current metrics. Use ohlcv for historical analysis.
DuckDB SQL syntax. Dates: DATE '2026-04-16'.
"""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You are QuantAI, a quantitative stock screening assistant for NSE India research.
You run SQL queries and present data. You do NOT give investment advice or recommendations.

DATABASE SCHEMA (DuckDB):
{DB_SCHEMA}

DUCKDB DATE SYNTAX (use exactly):
  date + INTERVAL 5 DAY          -- add 5 days
  date - INTERVAL 5 DAY          -- subtract 5 days
  DATE_DIFF('day', date1, date2)  -- difference in days
  STRFTIME(date, '%Y-%m')         -- format date
  DATE_TRUNC('month', date)       -- truncate to month
  CAST('2026-07-01' AS DATE)      -- literal date
  LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date)  -- 5-row lag

YOUR ONLY JOB:
- Translate the user's screening request into a SQL query
- Run it and present the results as a data table
- Add a brief factual note about what the data shows

STRICT RULES:
1. NEVER refuse a data/screening question. Always write SQL.
2. Questions about "likely to move", "candidates", "setup" = momentum screening query. Always answer with SQL.
3. Write ONE SQL query in ```sql ... ``` block. Then 2-3 factual sentences. STOP.
4. Conceptual questions: max 100 words. STOP.
5. Never say "I can't", "I'm sorry". You screen data, not predict.
6. SQL: LIMIT 30. Use signals for current, ohlcv for history.
7. Total response under 300 words.
8. For historical backtests: use LAG/LEAD window functions on ohlcv, not DATE_ADD.
"""

# ---------------------------------------------------------------------------
# Chat engine
# ---------------------------------------------------------------------------

class ChatEngine:
    def __init__(self) -> None:
        self._llm = LLMClient()
        self._store = get_store()

    def _market_summary(self) -> str:
        """One-line market context injected into every message."""
        try:
            df = self._store.get_signals()
            adv = int((df["pct_1d"] > 0).sum())
            dec = int((df["pct_1d"] < 0).sum())
            spikes = int(df["volume_spike"].sum())
            breaks = int(df["breakout"].sum())
            return (
                f"[Today's market: {len(df):,} stocks scanned | "
                f"Advancing: {adv} | Declining: {dec} | "
                f"Volume spikes: {spikes} | Breakouts: {breaks}]"
            )
        except Exception:
            return "[Market data available in DuckDB]"

    def _extract_sql(self, text: str) -> str | None:
        """Extract the first SQL block from an LLM response."""
        m = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # fallback: look for SELECT without fences
        m = re.search(r"(SELECT\s+.+?;)", text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _run_sql(self, sql: str) -> tuple[pd.DataFrame, str | None]:
        """Execute SQL against DuckDB. Returns (df, error_message)."""
        try:
            df = self._store.execute_sql(sql)
            return df, None
        except Exception as exc:
            return pd.DataFrame(), str(exc)

    def _df_to_chart_spec(self, df: pd.DataFrame, question: str) -> list[dict]:
        """Generate a simple chart spec from the result DataFrame."""
        charts = []
        # If there's a symbol column + one numeric column, make a bar chart
        if "symbol" in df.columns:
            num_cols = [c for c in df.columns if df[c].dtype in ("float64", "int64") and c != "symbol"]
            if num_cols:
                val_col = num_cols[0]
                data = [
                    {"name": str(row["symbol"]), "value": round(float(row[val_col]), 2)}
                    for _, row in df.head(20).iterrows()
                ]
                charts.append({
                    "type": "bar",
                    "title": f"{val_col} by stock",
                    "data": data,
                })
        return charts

    def _momentum_screen_fallback(self, question: str) -> dict[str, Any]:
        """Direct SQL screen used when the LLM refuses to answer."""
        sql = """
SELECT symbol, sector, last_close,
       momentum_score, continuation_prob, exhaustion_score, risk_score,
       pct_1d, pct_5d, volume_ratio, breakout_age, rsi_14
FROM signals
WHERE momentum_score >= 40
  AND continuation_prob >= 20
  AND exhaustion_score <= 25
  AND risk_score <= 40
ORDER BY continuation_prob DESC, momentum_score DESC
LIMIT 30
"""
        result_df, _ = self._run_sql(sql.strip())
        answer = (
            f"**Top {len(result_df)} risk-adjusted momentum candidates** — "
            f"high continuation probability, low exhaustion, low risk.\n\n"
            f"Sorted by empirical continuation probability (% of historical similar setups that gained ≥4%)."
        )
        charts = self._df_to_chart_spec(result_df, question)
        return {"answer": answer, "data": result_df.to_dict(orient="records"),
                "charts": charts, "sql": sql.strip()}

    def _reframe(self, question: str) -> str:
        """Reframe prediction-style questions as data screening requests."""
        triggers = ["will go up", "will rise", "will gain", "likely to move", "likely to go",
                    "possible stocks", "probability of", "predict", "forecast"]
        prefix = ("Screen for stocks with the strongest momentum signals today: high momentum_score, "
                  "volume_spike=true, breakout=true, above_50dma=true. Rank by momentum_score DESC. "
                  "Original request: ")
        q_lower = question.lower()
        if any(t in q_lower for t in triggers):
            return prefix + question
        return question

    def ask(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Process a user question. Returns:
          { "answer": str, "data": list[dict], "charts": list[dict], "sql": str|None }
        Single LLM call: model writes SQL + explanation together.
        """
        try:
            return self._ask_inner(question, history)
        except Exception as exc:
            log.exception("ChatEngine.ask() unhandled error")
            return {"answer": f"⚠️ Internal error: {exc}", "data": [], "charts": [], "sql": None}

    def _ask_inner(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        history = history or []

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in history[-4:]:
            messages.append({"role": turn["role"], "content": turn["content"]})

        reframed = self._reframe(question)
        messages.append({
            "role": "user",
            "content": f"{self._market_summary()}\n\nScreening request: {reframed}",
        })

        log.info("ChatEngine: calling LLM — %s", question[:80])
        try:
            llm_reply = self._llm.chat(messages, temperature=0.0)
        except Exception as exc:
            return {"answer": f"⚠️ LLM error: {exc}", "data": [], "charts": [], "sql": None}

        # If the model refused, fall back to a direct momentum screen
        refusal_phrases = ["i'm sorry", "i cannot", "i can't", "i don't provide",
                           "not able to", "unable to", "apologize"]
        if any(p in llm_reply.lower()[:120] for p in refusal_phrases):
            log.warning("LLM refused — running hardcoded momentum screen")
            return self._momentum_screen_fallback(question)

        # Extract and run SQL if the model produced one
        sql = self._extract_sql(llm_reply)
        result_df = pd.DataFrame()

        if sql:
            result_df, sql_error = self._run_sql(sql)
            log.info("SQL → %d rows  (error: %s)", len(result_df), sql_error)

            # Auto-fix: send the error back to the LLM once
            if sql_error:
                fix_messages = messages + [
                    {"role": "assistant", "content": llm_reply},
                    {"role": "user",
                     "content": f"The SQL failed:\n{sql_error}\nFix the SQL using correct DuckDB syntax and try again."},
                ]
                try:
                    fixed_reply = self._llm.chat(fix_messages, temperature=0.0)
                    fixed_sql = self._extract_sql(fixed_reply)
                    if fixed_sql:
                        result_df, sql_error2 = self._run_sql(fixed_sql)
                        if not sql_error2:
                            llm_reply = fixed_reply
                            sql = fixed_sql
                        else:
                            llm_reply += f"\n\n> ⚠️ SQL error: `{sql_error2}`"
                    else:
                        llm_reply += f"\n\n> ⚠️ SQL error: `{sql_error}`"
                except Exception:
                    llm_reply += f"\n\n> ⚠️ SQL error: `{sql_error}`"

        charts = self._df_to_chart_spec(result_df, question) if not result_df.empty else []

        return {
            "answer": llm_reply,
            "data":   result_df.to_dict(orient="records") if not result_df.empty else [],
            "charts": charts,
            "sql":    sql,
        }


# Module-level singleton
_engine: ChatEngine | None = None


def get_engine() -> ChatEngine:
    global _engine
    if _engine is None:
        _engine = ChatEngine()
    return _engine

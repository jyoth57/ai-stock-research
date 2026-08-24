"""chat router — DeepSeek-powered Text-to-SQL AI over NSE DuckDB data"""
from __future__ import annotations
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from src.core.settings import settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    history:  list[dict] = []


def _llm_available() -> bool:
    return bool(
        (settings.llm_provider == "watsonx"
         and settings.watsonx_url
         and settings.watsonx_project_id
         and (settings.watsonx_token or (settings.watsonx_username and settings.watsonx_api_key)))
        or (settings.llm_provider == "deepseek" and settings.deepseek_api_key)
        or (settings.llm_provider == "openai"   and settings.openai_api_key)
        or (settings.llm_provider == "ollama")
    )


@router.post("")
def chat(req: ChatRequest):
    # ── LLM path ──────────────────────────────────────────────────────────
    if _llm_available():
        try:
            from src.ai.chat_engine import get_engine
            result = get_engine().ask(req.question, req.history)
            return result
        except Exception as exc:
            log.error("LLM chat failed: %s", exc)
            return {
                "answer": f"⚠️ LLM error: {exc}",
                "data": [], "charts": [], "sql": None,
            }

    # ── Fallback: rule-based when no API key is configured ────────────────
    log.warning("No LLM API key configured — using rule-based fallback")
    return _rule_based(req.question)


def _rule_based(q: str) -> dict:
    """Fast pattern-matching fallback used when no LLM key is set."""
    from src.database.duckdb_store import get_store
    q = q.lower()
    store = get_store()
    df = store.get_signals()

    if any(w in q for w in ["8%", "10%", "mover", "move", "gain"]):
        threshold = 10 if "10%" in q else 8
        result = df[df["pct_1d"].abs() >= threshold]
        return {"answer": f"Found **{len(result)} stocks** that moved ≥{threshold}% in the last session.", "data": result.to_dict(orient="records"), "charts": [], "sql": None}

    if any(w in q for w in ["volume spike", "vol"]):
        result = df[df["volume_spike"]].sort_values("volume_ratio", ascending=False)
        chart = {"type": "bar", "title": "Top Volume Spikes", "data": [{"name": r["symbol"], "value": round(r["volume_ratio"], 1)} for r in result.head(15).to_dict(orient="records")]}
        return {"answer": f"Found **{len(result)} volume spike stocks** (>2× avg volume).", "data": result.head(30).to_dict(orient="records"), "charts": [chart], "sql": None}

    if "breakout" in q:
        result = df[df["breakout"]].sort_values("momentum_score", ascending=False)
        return {"answer": f"Found **{len(result)} breakout stocks**.", "data": result.head(30).to_dict(orient="records"), "charts": [], "sql": None}

    if any(w in q for w in ["top", "best", "momentum", "score"]):
        result = df.head(20)
        chart = {"type": "bar", "title": "Top 20 Momentum Scores", "data": [{"name": r["symbol"], "value": round(r["momentum_score"], 1)} for r in result.to_dict(orient="records")]}
        return {"answer": f"Top **20 momentum stocks** by composite score.", "data": result.to_dict(orient="records"), "charts": [chart], "sql": None}

    adv = int((df["pct_1d"] > 0).sum())
    dec = int((df["pct_1d"] < 0).sum())
    return {
        "answer": (
            f"**Market summary** — {len(df):,} stocks scanned:\n\n"
            f"- 📈 Advancing: **{adv}**\n"
            f"- 📉 Declining: **{dec}**\n"
            f"- ⚡ Volume spikes: **{int(df['volume_spike'].sum())}**\n"
            f"- 🔥 Breakouts: **{int(df['breakout'].sum())}**\n\n"
            f"💡 *Add your `DEEPSEEK_API_KEY` to `.env` to unlock full AI chat.*"
        ),
        "data": [], "charts": [], "sql": None,
    }


    # ── Pattern matching ───────────────────────────────────────────────────
    if any(w in q for w in ["move", "mover", "8%", "10%", "gain"]):
        threshold = 10 if "10%" in q else 8
        result = df[df["pct_1d"].abs() >= threshold].reset_index()
        answer = (
            f"Found **{len(result)} stocks** that moved ≥{threshold}% in the last session.\n\n"
            f"These are sorted by absolute move."
        )
        return {"answer": answer, "data": result.to_dict(orient="records"), "charts": []}

    if any(w in q for w in ["volume spike", "volume", "vol"]):
        result = df[df["volume_spike"]].sort_values("volume_ratio", ascending=False).reset_index()
        answer = (
            f"Found **{len(result)} stocks** with volume spike (>2× 20-day average).\n\n"
            f"Top movers by volume ratio are listed below."
        )
        chart = {
            "type": "bar",
            "title": "Top 15 Volume Spikes",
            "data": [{"name": r["symbol"], "value": round(r["volume_ratio"], 1)} for r in result.head(15).to_dict(orient="records")],
        }
        return {"answer": answer, "data": result.head(30).to_dict(orient="records"), "charts": [chart]}

    if "breakout" in q:
        result = df[df["breakout"]].sort_values("momentum_score", ascending=False).reset_index()
        answer = (
            f"Found **{len(result)} breakout stocks** (closing above prior 20-day resistance).\n\n"
            f"Filtered to those with the highest momentum score."
        )
        return {"answer": answer, "data": result.head(30).to_dict(orient="records"), "charts": []}

    if any(w in q for w in ["momentum", "score", "top", "best"]):
        result = df.sort_values("momentum_score", ascending=False).head(20).reset_index()
        chart = {
            "type": "bar",
            "title": "Top 20 Momentum Scores",
            "data": [{"name": r["symbol"], "value": round(r["momentum_score"], 1)} for r in result.to_dict(orient="records")],
        }
        answer = (
            f"Here are the **top {len(result)} momentum stocks** ranked by composite score (0–100).\n\n"
            f"Score factors: trend, volume, position vs 52W high, and relative strength."
        )
        return {"answer": answer, "data": result.to_dict(orient="records"), "charts": [chart]}

    if any(w in q for w in ["sector", "rotation"]):
        answer = (
            "**Sector rotation analysis** requires a sector mapping file.\n\n"
            "Currently, the platform has OHLCV data for all NSE-listed equities. "
            "Add a sector mapping CSV to `data/raw/sector_map.csv` to enable this feature."
        )
        return {"answer": answer, "data": [], "charts": []}

    if any(w in q for w in ["explain", "how", "score", "methodology"]):
        answer = (
            "## Momentum Score Methodology\n\n"
            "The score is a composite 0–100 indicator built from:\n\n"
            "| Factor | Weight | Description |\n"
            "|--------|--------|-------------|\n"
            "| 20-day return | up to 20 pts | Trend strength |\n"
            "| 5-day return | up to 10 pts | Short-term momentum |\n"
            "| Above 50 DMA | 10 pts | Trend filter |\n"
            "| Volume ratio | up to 15 pts | Institutional interest |\n"
            "| Volume spike | 10 pts | Unusual activity |\n"
            "| Near 52W high | 10 pts | Strength filter |\n"
            "| Breakout | 10 pts | Resistance cleared |\n"
            "| Higher lows | 10 pts | Relative strength |\n"
            "| 1-day return | up to 5 pts | Recent strength |"
        )
        return {"answer": answer, "data": [], "charts": []}

    # ── Default: return market summary ────────────────────────────────────
    advancing = int((df["pct_1d"] > 0).sum())
    declining  = int((df["pct_1d"] < 0).sum())
    answer = (
        f"Based on today's NSE scan of **{len(df):,} stocks**:\n\n"
        f"- 📈 **{advancing}** advancing\n"
        f"- 📉 **{declining}** declining\n"
        f"- ⚡ **{int(df['volume_spike'].sum())}** volume spikes\n"
        f"- 🔥 **{int(df['breakout'].sum())}** breakouts\n\n"
        f"Try asking: _'Show me stocks that moved >8%'_ or _'Find breakouts with volume spike'_"
    )
    return {"answer": answer, "data": [], "charts": []}

"""fundamental_agent.py
----------------------
Analyses a stock's business quality, financial health, and growth
using fundamentals data + RAG knowledge + LLM reasoning.

Usage
-----
    from src.agents import FundamentalAgent

    agent = FundamentalAgent()
    analysis = agent.analyse("TCS")
    print(analysis)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel

from src.core.logging import get_logger
from src.core.exceptions import DataNotFoundError
from src.market.sector_data import get_sector
from src.financials.ratios import RatiosEngine, compute_piotroski
from src.scoring.overall import score_stock, ScoreCard

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for structured LLM output
# ---------------------------------------------------------------------------

class _LLMFundamentalOutput(BaseModel):
    business_model_summary: str
    revenue_trend_commentary: str
    profitability_commentary: str
    balance_sheet_commentary: str
    key_strengths: list[str]
    key_concerns: list[str]
    quality_verdict: Literal["Excellent", "Good", "Average", "Poor"]
    moat_assessment: str


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FundamentalAnalysis:
    symbol: str
    sector: str
    latest_date: str

    # Core metrics
    roe_pct: float
    roce_pct: float
    eps_growth_pct: float
    revenue_cagr_pct: float
    debt_to_equity: float
    free_cash_flow: float
    net_margin: float
    piotroski_score: int
    piotroski_signals: dict

    # Composite scores
    score_card: ScoreCard

    # LLM-generated (populated only when OpenAI key is configured)
    business_model_summary: str = ""
    revenue_trend_commentary: str = ""
    profitability_commentary: str = ""
    balance_sheet_commentary: str = ""
    key_strengths: list[str] = field(default_factory=list)
    key_concerns: list[str] = field(default_factory=list)
    quality_verdict: str = "N/A (LLM not configured)"
    moat_assessment: str = ""

    def __str__(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"FUNDAMENTAL ANALYSIS: {self.symbol} ({self.sector})",
            f"{'='*60}",
            f"As of: {self.latest_date}",
            f"",
            f"--- Quantitative Metrics ---",
            f"  ROE:             {self.roe_pct:.1f}%",
            f"  ROCE:            {self.roce_pct:.1f}%",
            f"  Revenue CAGR:    {self.revenue_cagr_pct:.1f}%",
            f"  EPS Growth:      {self.eps_growth_pct:.1f}%",
            f"  Net Margin:      {self.net_margin:.1f}%",
            f"  Debt/Equity:     {self.debt_to_equity:.2f}x",
            f"  Free Cash Flow:  {self.free_cash_flow:,.0f}",
            f"  Piotroski Score: {self.piotroski_score}/7",
            f"",
            str(self.score_card),
        ]
        if self.key_strengths:
            lines += ["\n--- AI Analysis ---", f"Verdict: {self.quality_verdict}"]
            lines += ["Strengths:"] + [f"  + {s}" for s in self.key_strengths]
            lines += ["Concerns:"]  + [f"  - {c}" for c in self.key_concerns]
            if self.moat_assessment:
                lines.append(f"Moat: {self.moat_assessment}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FundamentalAgent:
    """Fundamental analysis agent.

    Parameters
    ----------
    use_llm: Set to False to skip LLM call and return quant-only analysis.
    """

    def __init__(self, use_llm: bool = True) -> None:
        self._use_llm = use_llm
        self._engine = RatiosEngine()

    def analyse(self, symbol: str) -> FundamentalAnalysis:
        """Run a full fundamental analysis for *symbol*.

        Loads enriched fundamentals, computes scores, retrieves relevant
        knowledge via RAG, and calls the LLM for qualitative commentary.

        Raises
        ------
        DataNotFoundError
            If no fundamentals data exists for the symbol.
        """
        sym = symbol.strip().upper()
        log.info("FundamentalAgent: analysing %s", sym)

        # 1. Load data
        df = self._engine.load(symbol=sym)
        if df.empty:
            raise DataNotFoundError(f"No fundamentals data for {sym}.")

        latest = df.sort_values("date").iloc[-1]
        sector = get_sector(sym)

        # 2. Piotroski
        try:
            p = compute_piotroski(df, sym)
            p_score = p["score"]
            p_signals = p["signals"]
        except Exception:
            p_score, p_signals = 0, {}

        # 3. Composite score
        card = score_stock(latest)

        analysis = FundamentalAnalysis(
            symbol=sym,
            sector=sector,
            latest_date=str(latest.get("date", ""))[:10],
            roe_pct=float(latest.get("roe_pct") or 0),
            roce_pct=float(latest.get("roce_pct") or 0),
            eps_growth_pct=float(latest.get("eps_growth_pct") or 0),
            revenue_cagr_pct=float(latest.get("revenue_cagr_pct") or 0),
            debt_to_equity=float(latest.get("debt_to_equity") or 0),
            free_cash_flow=float(latest.get("free_cash_flow") or 0),
            net_margin=float(latest.get("net_margin") or 0),
            piotroski_score=p_score,
            piotroski_signals=p_signals,
            score_card=card,
        )

        # 4. LLM analysis (optional)
        if self._use_llm:
            analysis = self._enrich_with_llm(analysis, latest, df)

        return analysis

    def _enrich_with_llm(
        self,
        analysis: FundamentalAnalysis,
        latest,
        df,
    ) -> FundamentalAnalysis:
        try:
            from src.ai.rag import KnowledgeRetriever
            from src.ai.llm import LLMClient
        except ImportError:
            log.warning("AI modules not available — returning quant-only analysis")
            return analysis

        try:
            retriever = KnowledgeRetriever()
            client = LLMClient()
        except Exception as exc:
            log.warning("LLM/RAG init failed: %s", exc)
            return analysis

        # RAG: pull relevant knowledge
        query = (
            f"How to evaluate fundamental quality of a {analysis.sector} company "
            f"with ROCE {analysis.roce_pct:.0f}%, ROE {analysis.roe_pct:.0f}%, "
            f"and Debt/Equity {analysis.debt_to_equity:.1f}x?"
        )
        context = retriever.get_context(query, top_k=5)

        # Build prompt
        metrics_block = (
            f"Symbol: {analysis.symbol} | Sector: {analysis.sector}\n"
            f"ROE: {analysis.roe_pct:.1f}% | ROCE: {analysis.roce_pct:.1f}% "
            f"| Revenue CAGR: {analysis.revenue_cagr_pct:.1f}% "
            f"| EPS Growth: {analysis.eps_growth_pct:.1f}%\n"
            f"Net Margin: {analysis.net_margin:.1f}% | D/E: {analysis.debt_to_equity:.2f}x "
            f"| FCF: {analysis.free_cash_flow:,.0f}\n"
            f"Piotroski Score: {analysis.piotroski_score}/7\n"
            f"Composite Score: {analysis.score_card.composite}/100 (Grade {analysis.score_card.grade})"
        )

        prompt = (
            f"Analyse the fundamental quality of this Indian listed company:\n\n"
            f"{metrics_block}\n\n"
            f"Provide: business model summary, revenue trend commentary, "
            f"profitability commentary, balance sheet commentary, "
            f"3-5 key strengths, 2-4 key concerns, quality verdict, "
            f"and a one-sentence moat assessment."
        )

        messages = client.build_messages(prompt, system_key="fundamental", context=context)

        try:
            output: _LLMFundamentalOutput = client.structured_chat(
                messages, response_model=_LLMFundamentalOutput
            )
            analysis.business_model_summary  = output.business_model_summary
            analysis.revenue_trend_commentary = output.revenue_trend_commentary
            analysis.profitability_commentary  = output.profitability_commentary
            analysis.balance_sheet_commentary  = output.balance_sheet_commentary
            analysis.key_strengths             = output.key_strengths
            analysis.key_concerns              = output.key_concerns
            analysis.quality_verdict           = output.quality_verdict
            analysis.moat_assessment           = output.moat_assessment
        except Exception as exc:
            log.warning("LLM fundamental analysis failed: %s", exc)

        return analysis

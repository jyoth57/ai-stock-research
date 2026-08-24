"""chief_investment_officer.py
------------------------------
Orchestrates all domain agents and synthesises a single investment
recommendation: BUY / HOLD / AVOID.

Pipeline
--------
    FundamentalAgent  ─┬─>
    ValuationAgent    ─┼─> ChiefInvestmentOfficer ─> InvestmentRecommendation
    RiskAgent         ─┘

Usage
-----
    from src.agents import ChiefInvestmentOfficer

    cio = ChiefInvestmentOfficer()
    rec = cio.recommend("TCS", current_price=4200.0)
    print(rec)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel

from src.core.logging import get_logger
from src.core.exceptions import DataNotFoundError
from src.market.sector_data import get_sector
from .fundamental_agent import FundamentalAgent, FundamentalAnalysis
from .valuation_agent import ValuationAgent, ValuationAnalysis
from .risk_agent import RiskAgent, RiskAnalysis

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# LLM output schema for the CIO synthesis
# ---------------------------------------------------------------------------

class _CIOSynthesis(BaseModel):
    recommendation: Literal["BUY", "HOLD", "AVOID"]
    conviction: Literal["High", "Medium", "Low"]
    investment_thesis: str          # 2-3 sentence core thesis
    key_catalysts: list[str]        # what must go right
    key_risks: list[str]            # what could go wrong
    price_target_comment: str       # commentary on fair value vs. current price
    time_horizon: str               # e.g. "12-18 months"
    portfolio_sizing_suggestion: str  # e.g. "3-5% of portfolio"
    full_reasoning: str             # detailed reasoning paragraph


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class InvestmentRecommendation:
    symbol: str
    sector: str
    current_price: Optional[float]

    # Sub-agent outputs
    fundamental: FundamentalAnalysis
    valuation: ValuationAnalysis
    risk: RiskAnalysis

    # Composite score (averaged across agents)
    composite_score: float

    # CIO decision
    recommendation: str = "PENDING"
    conviction: str = "N/A"
    investment_thesis: str = ""
    key_catalysts: list[str] = field(default_factory=list)
    key_risks: list[str] = field(default_factory=list)
    price_target_comment: str = ""
    time_horizon: str = ""
    portfolio_sizing_suggestion: str = ""
    full_reasoning: str = ""

    # Rule-based fallback recommendation
    rule_based_recommendation: str = ""

    def __str__(self) -> str:
        lines = [
            f"\n{'#'*60}",
            f"INVESTMENT RECOMMENDATION: {self.symbol}",
            f"{'#'*60}",
            f"Sector: {self.sector}",
            f"Current Price: {f'INR {self.current_price:,.0f}' if self.current_price else 'N/A'}",
            f"Composite Score: {self.composite_score:.0f}/100",
            f"",
            f"  RECOMMENDATION: {self.recommendation}",
            f"  Conviction:     {self.conviction}",
            f"",
            f"Sub-agent scores:",
            f"  Fundamental:  {self.fundamental.score_card.composite:.0f}/100 (Grade {self.fundamental.score_card.grade})",
            f"  Valuation:    {self.valuation.valuation_score:.0f}/100",
            f"  Risk:         {self.risk.risk_score:.0f}/100",
        ]
        if self.investment_thesis:
            lines += [
                f"",
                f"Thesis: {self.investment_thesis}",
                f"Time Horizon: {self.time_horizon}",
                f"Sizing: {self.portfolio_sizing_suggestion}",
            ]
        if self.key_catalysts:
            lines += ["\nKey Catalysts:"] + [f"  ✓ {c}" for c in self.key_catalysts]
        if self.key_risks:
            lines += ["Key Risks:"] + [f"  ✕ {r}" for r in self.key_risks]
        if self.full_reasoning:
            lines += [f"\nReasoning: {self.full_reasoning}"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CIO Agent
# ---------------------------------------------------------------------------

class ChiefInvestmentOfficer:
    """Orchestrates all domain agents and issues a final recommendation.

    Parameters
    ----------
    use_llm: Set to False to use rule-based recommendation only.
    """

    def __init__(self, use_llm: bool = True) -> None:
        self._use_llm = use_llm
        self._fund_agent = FundamentalAgent(use_llm=use_llm)
        self._val_agent  = ValuationAgent(use_llm=use_llm)
        self._risk_agent = RiskAgent(use_llm=use_llm)

    def recommend(
        self,
        symbol: str,
        current_price: Optional[float] = None,
    ) -> InvestmentRecommendation:
        """Run all domain agents and return a final investment recommendation.

        Parameters
        ----------
        symbol:        Bare NSE symbol (e.g. ``"TCS"``)
        current_price: Current market price in INR (optional, improves valuation analysis)

        Returns
        -------
        InvestmentRecommendation
        """
        sym = symbol.strip().upper()
        sector = get_sector(sym)
        log.info("CIO: starting full analysis for %s", sym)
        t0 = time.perf_counter()

        # 1. Run all domain agents
        fundamental = self._run_fundamental(sym)
        valuation   = self._run_valuation(sym, current_price)
        risk        = self._run_risk(sym)

        # 2. Composite score: weighted average of agent scores
        composite = (
            fundamental.score_card.composite * 0.45
            + valuation.valuation_score        * 0.30
            + risk.risk_score                  * 0.25
        )

        rec = InvestmentRecommendation(
            symbol=sym,
            sector=sector,
            current_price=current_price,
            fundamental=fundamental,
            valuation=valuation,
            risk=risk,
            composite_score=round(composite, 1),
        )

        # 3. Rule-based recommendation (always computed as fallback)
        rec.rule_based_recommendation = self._rule_based(rec)
        rec.recommendation = rec.rule_based_recommendation
        rec.conviction = self._rule_conviction(rec)

        # 4. LLM synthesis (optional)
        if self._use_llm:
            rec = self._synthesise_with_llm(rec)

        elapsed = time.perf_counter() - t0
        log.info("CIO: completed %s in %.1fs  →  %s", sym, elapsed, rec.recommendation)
        return rec

    # ------------------------------------------------------------------
    # Domain agent runners (with error handling)
    # ------------------------------------------------------------------

    def _run_fundamental(self, sym: str) -> FundamentalAnalysis:
        try:
            return self._fund_agent.analyse(sym)
        except DataNotFoundError as exc:
            log.error("Fundamental agent failed for %s: %s", sym, exc)
            raise

    def _run_valuation(self, sym: str, price) -> ValuationAnalysis:
        try:
            return self._val_agent.analyse(sym, current_price=price)
        except DataNotFoundError:
            raise
        except Exception as exc:
            log.warning("Valuation agent failed for %s: %s", sym, exc)
            # Return minimal valuation
            from src.agents.valuation_agent import ValuationAnalysis as VA
            return VA(
                symbol=sym, sector=get_sector(sym), latest_date="",
                current_price=price, valuation_score=50.0,
                pe_ratio=None, peg_ratio=None, fcf_yield_proxy=0.0,
                roce_pct=0.0, revenue_cagr_pct=0.0, dcf_fair_value_estimate=None,
            )

    def _run_risk(self, sym: str) -> RiskAnalysis:
        try:
            return self._risk_agent.analyse(sym)
        except DataNotFoundError:
            raise
        except Exception as exc:
            log.warning("Risk agent failed for %s: %s", sym, exc)
            from src.agents.risk_agent import RiskAnalysis as RA
            return RA(
                symbol=sym, sector=get_sector(sym), latest_date="",
                risk_score=50.0, debt_to_equity=0.0,
                earnings_quality_ratio=0.0, free_cash_flow=0.0,
                net_income=0.0, leverage_score=50.0, fcf_cover_score=50.0,
            )

    # ------------------------------------------------------------------
    # Rule-based decision
    # ------------------------------------------------------------------

    def _rule_based(self, rec: InvestmentRecommendation) -> str:
        """Issue a recommendation based on score thresholds."""
        score = rec.composite_score
        risk  = rec.risk.risk_score
        flags = len(rec.risk.auto_red_flags)

        # Hard blocks
        if flags >= 3 or risk < 25:
            return "AVOID"
        if rec.fundamental.score_card.grade == "F":
            return "AVOID"

        # Score-based
        if score >= 65 and risk >= 50:
            return "BUY"
        if score >= 45:
            return "HOLD"
        return "AVOID"

    def _rule_conviction(self, rec: InvestmentRecommendation) -> str:
        if rec.composite_score >= 75 and rec.risk.risk_score >= 65:
            return "High"
        if rec.composite_score >= 55:
            return "Medium"
        return "Low"

    # ------------------------------------------------------------------
    # LLM synthesis
    # ------------------------------------------------------------------

    def _synthesise_with_llm(
        self, rec: InvestmentRecommendation
    ) -> InvestmentRecommendation:
        try:
            from src.ai.rag import KnowledgeRetriever
            from src.ai.llm import LLMClient
            retriever = KnowledgeRetriever()
            client = LLMClient()
        except Exception as exc:
            log.warning("LLM/RAG init failed: %s", exc)
            return rec

        # Get relevant investment principles for this sector
        context_q = (
            f"investment decision criteria for {rec.sector} sector stocks. "
            f"When to buy, hold, or avoid. Margin of safety."
        )
        context = retriever.get_context(context_q, top_k=6)

        summary = (
            f"=== ANALYSIS SUMMARY FOR {rec.symbol} ===\n"
            f"Sector: {rec.sector} | Composite Score: {rec.composite_score}/100\n"
            f"\nFUNDAMENTAL (score {rec.fundamental.score_card.composite}/100, Grade {rec.fundamental.score_card.grade}):\n"
            f"  ROE: {rec.fundamental.roe_pct:.1f}%  ROCE: {rec.fundamental.roce_pct:.1f}%  "
            f"Rev CAGR: {rec.fundamental.revenue_cagr_pct:.1f}%  EPS Growth: {rec.fundamental.eps_growth_pct:.1f}%\n"
            f"  D/E: {rec.fundamental.debt_to_equity:.2f}x  Piotroski: {rec.fundamental.piotroski_score}/7\n"
            f"  Quality Verdict: {rec.fundamental.quality_verdict}\n"
            f"  Moat: {rec.fundamental.moat_assessment}\n"
            f"\nVALUATION (score {rec.valuation.valuation_score}/100):\n"
            f"  Price: {rec.current_price or 'N/A'}  FCF/Rev: {rec.valuation.fcf_yield_proxy:.1f}%\n"
            f"  AI Verdict: {rec.valuation.verdict}  Fair Value: {rec.valuation.fair_value_range or 'N/A'}\n"
            f"\nRISK (score {rec.risk.risk_score}/100):\n"
            f"  Risk Level: {rec.risk.risk_level}  D/E: {rec.risk.debt_to_equity:.2f}x\n"
            f"  Red Flags: {rec.risk.auto_red_flags or 'None detected'}\n"
            f"\nRule-based recommendation: {rec.rule_based_recommendation} ({rec.conviction} conviction)"
        )

        prompt = (
            f"As Chief Investment Officer, synthesise this full analysis into a final "
            f"investment recommendation for {rec.symbol}:\n\n{summary}\n\n"
            f"Issue a BUY, HOLD, or AVOID recommendation with conviction level, "
            f"investment thesis, key catalysts, key risks, price target commentary, "
            f"time horizon, portfolio sizing suggestion, and detailed reasoning."
        )

        messages = client.build_messages(prompt, system_key="cio", context=context)
        try:
            out: _CIOSynthesis = client.structured_chat(messages, _CIOSynthesis)
            rec.recommendation              = out.recommendation
            rec.conviction                  = out.conviction
            rec.investment_thesis           = out.investment_thesis
            rec.key_catalysts               = out.key_catalysts
            rec.key_risks                   = out.key_risks
            rec.price_target_comment        = out.price_target_comment
            rec.time_horizon                = out.time_horizon
            rec.portfolio_sizing_suggestion = out.portfolio_sizing_suggestion
            rec.full_reasoning              = out.full_reasoning
        except Exception as exc:
            log.warning("CIO LLM synthesis failed: %s  (using rule-based)", exc)

        return rec

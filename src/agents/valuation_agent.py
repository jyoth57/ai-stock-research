"""valuation_agent.py
--------------------
Estimates intrinsic value using FCF-based DCF, ROCE-justified multiples,
and PEG-based screening. Retrieves valuation knowledge via RAG.

Usage
-----
    from src.agents import ValuationAgent

    agent = ValuationAgent()
    result = agent.analyse("INFY", current_price=1800.0)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel

from src.core.logging import get_logger
from src.core.exceptions import DataNotFoundError
from src.market.sector_data import get_sector
from src.financials.ratios import RatiosEngine
from src.scoring.valuation import valuation_score, valuation_score_with_price

log = get_logger(__name__)


class _LLMValuationOutput(BaseModel):
    valuation_method_rationale: str
    dcf_commentary: str
    multiple_commentary: str
    fair_value_range: str       # e.g. "1600 - 2000"
    upside_downside: str        # e.g. "+12% to +35%"
    margin_of_safety: str       # e.g. "Adequate (15%)"
    verdict: Literal["Cheap", "Fair", "Slightly Expensive", "Expensive", "Very Expensive"]
    key_assumptions: list[str]


@dataclass
class ValuationAnalysis:
    symbol: str
    sector: str
    latest_date: str
    current_price: Optional[float]

    # Quant valuation
    valuation_score: float
    pe_ratio: Optional[float]
    peg_ratio: Optional[float]
    fcf_yield_proxy: float     # FCF/Revenue %
    roce_pct: float
    revenue_cagr_pct: float

    # Rough DCF estimate (simplified)
    dcf_fair_value_estimate: Optional[float]

    # LLM output
    fair_value_range: str = ""
    upside_downside: str = ""
    margin_of_safety: str = ""
    verdict: str = "N/A"
    valuation_method_rationale: str = ""
    dcf_commentary: str = ""
    multiple_commentary: str = ""
    key_assumptions: list = None  # type: ignore

    def __post_init__(self):
        if self.key_assumptions is None:
            self.key_assumptions = []

    def __str__(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"VALUATION ANALYSIS: {self.symbol} ({self.sector})",
            f"{'='*60}",
            f"Current Price: {f'INR {self.current_price:,.0f}' if self.current_price else 'N/A'}",
            f"Valuation Score: {self.valuation_score}/100",
            f"P/E Ratio: {f'{self.pe_ratio:.1f}x' if self.pe_ratio else 'N/A'}",
            f"PEG Ratio: {f'{self.peg_ratio:.2f}' if self.peg_ratio else 'N/A'}",
            f"FCF/Revenue Proxy: {self.fcf_yield_proxy:.1f}%",
            f"DCF Estimate: {f'INR {self.dcf_fair_value_estimate:,.0f}' if self.dcf_fair_value_estimate else 'N/A'}",
        ]
        if self.verdict != "N/A":
            lines += [
                f"\nAI Verdict: {self.verdict}",
                f"Fair Value Range: {self.fair_value_range}",
                f"Upside/Downside: {self.upside_downside}",
                f"Margin of Safety: {self.margin_of_safety}",
            ]
        return "\n".join(lines)


class ValuationAgent:
    """Valuation analysis agent."""

    def __init__(self, use_llm: bool = True) -> None:
        self._use_llm = use_llm
        self._engine = RatiosEngine()

    def analyse(
        self,
        symbol: str,
        current_price: Optional[float] = None,
    ) -> ValuationAnalysis:
        sym = symbol.strip().upper()
        log.info("ValuationAgent: analysing %s (price=%s)", sym, current_price)

        df = self._engine.load(symbol=sym)
        if df.empty:
            raise DataNotFoundError(f"No fundamentals data for {sym}.")

        latest = df.sort_values("date").iloc[-1]
        sector = get_sector(sym)

        # Quant valuation score
        if current_price:
            v = valuation_score_with_price(latest, current_price)
        else:
            v = valuation_score(latest)

        fcf = float(latest.get("free_cash_flow") or 0)
        revenue = float(latest.get("revenue") or 1)
        fcf_yield_proxy = fcf / revenue * 100

        # Simplified DCF: FCF * (1 + g) / (WACC - g)
        # Uses WACC=13%, g=revenue_cagr (capped at 10%), terminal g=5%
        dcf_estimate = self._simple_dcf(latest)

        result = ValuationAnalysis(
            symbol=sym,
            sector=sector,
            latest_date=str(latest.get("date", ""))[:10],
            current_price=current_price,
            valuation_score=v["score"],
            pe_ratio=v.get("pe_ratio"),
            peg_ratio=v.get("peg_ratio"),
            fcf_yield_proxy=round(fcf_yield_proxy, 1),
            roce_pct=float(latest.get("roce_pct") or 0),
            revenue_cagr_pct=float(latest.get("revenue_cagr_pct") or 0),
            dcf_fair_value_estimate=dcf_estimate,
        )

        if self._use_llm:
            result = self._enrich_with_llm(result, latest)

        return result

    def _simple_dcf(
        self,
        row,
        wacc: float = 0.13,
        terminal_growth: float = 0.05,
    ) -> Optional[float]:
        """Rough single-stage DCF using latest FCF and revenue CAGR as growth proxy."""
        fcf = float(row.get("free_cash_flow") or 0)
        if fcf <= 0:
            return None
        rev_cagr_pct = float(row.get("revenue_cagr_pct") or 0)
        growth = min(rev_cagr_pct / 100, 0.10)   # cap at 10%
        if wacc <= terminal_growth:
            return None
        # Terminal value = FCF * (1 + g) / (WACC - g)
        terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
        # Phase 1: 5 years at growth rate
        phase1 = sum(fcf * (1 + growth) ** t / (1 + wacc) ** t for t in range(1, 6))
        # Phase 2: terminal value discounted back 5 years
        phase2 = terminal_value / (1 + wacc) ** 5
        return round(phase1 + phase2, 0)

    def _enrich_with_llm(self, result: ValuationAnalysis, latest) -> ValuationAnalysis:
        try:
            from src.ai.rag import KnowledgeRetriever
            from src.ai.llm import LLMClient
            retriever = KnowledgeRetriever()
            client = LLMClient()
        except Exception as exc:
            log.warning("LLM/RAG init failed: %s", exc)
            return result

        query = f"Valuation methods for {result.sector} stocks with ROCE {result.roce_pct:.0f}%"
        context = retriever.get_context(query, top_k=4)

        metrics = (
            f"Symbol: {result.symbol} | Sector: {result.sector}\n"
            f"ROCE: {result.roce_pct:.1f}% | Revenue CAGR: {result.revenue_cagr_pct:.1f}%\n"
            f"FCF/Revenue: {result.fcf_yield_proxy:.1f}% | "
            f"Current Price: {f'INR {result.current_price:,.0f}' if result.current_price else 'not provided'}\n"
            f"P/E: {result.pe_ratio or 'N/A'} | PEG: {result.peg_ratio or 'N/A'}\n"
            f"Simplified DCF estimate: {f'INR {result.dcf_fair_value_estimate:,.0f}' if result.dcf_fair_value_estimate else 'N/A'}"
        )
        prompt = (
            f"Provide a valuation analysis for this Indian listed stock:\n\n{metrics}\n\n"
            f"Include: valuation method rationale, DCF commentary, multiple commentary, "
            f"estimated fair value range (in INR), upside/downside from current price, "
            f"margin of safety assessment, overall verdict, and 3-4 key assumptions."
        )

        messages = client.build_messages(prompt, system_key="valuation", context=context)
        try:
            out: _LLMValuationOutput = client.structured_chat(messages, _LLMValuationOutput)
            result.valuation_method_rationale = out.valuation_method_rationale
            result.dcf_commentary = out.dcf_commentary
            result.multiple_commentary = out.multiple_commentary
            result.fair_value_range = out.fair_value_range
            result.upside_downside = out.upside_downside
            result.margin_of_safety = out.margin_of_safety
            result.verdict = out.verdict
            result.key_assumptions = out.key_assumptions
        except Exception as exc:
            log.warning("LLM valuation failed: %s", exc)
        return result

"""risk_agent.py
---------------
Identifies financial red flags, governance concerns, and business risks.
Uses red flag knowledge from RAG + quantitative risk scoring.

Usage
-----
    from src.agents import RiskAgent

    agent = RiskAgent()
    result = agent.analyse("ADANIENT")
    print(result)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from src.core.logging import get_logger
from src.core.exceptions import DataNotFoundError
from src.market.sector_data import get_sector
from src.financials.ratios import RatiosEngine
from src.scoring.risk import risk_score

log = get_logger(__name__)


class _LLMRiskOutput(BaseModel):
    quantitative_red_flags: list[str]
    governance_concerns: list[str]
    business_risks: list[str]
    macro_risks: list[str]
    risk_level: Literal["Low", "Medium", "High", "Very High"]
    risk_summary: str
    mitigants: list[str]


@dataclass
class RiskAnalysis:
    symbol: str
    sector: str
    latest_date: str

    # Quant risk metrics
    risk_score: float              # 0-100, 100 = safest
    debt_to_equity: float
    earnings_quality_ratio: float
    free_cash_flow: float
    net_income: float
    leverage_score: float
    fcf_cover_score: float

    # Automated red flags detected from data
    auto_red_flags: list[str] = field(default_factory=list)

    # LLM output
    quantitative_red_flags: list[str] = field(default_factory=list)
    governance_concerns: list[str] = field(default_factory=list)
    business_risks: list[str] = field(default_factory=list)
    macro_risks: list[str] = field(default_factory=list)
    risk_level: str = "N/A"
    risk_summary: str = ""
    mitigants: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"RISK ANALYSIS: {self.symbol} ({self.sector})",
            f"{'='*60}",
            f"Risk Score: {self.risk_score}/100  (100 = lowest risk)",
            f"Debt/Equity: {self.debt_to_equity:.2f}x",
            f"Earnings Quality (FCF/NI): {self.earnings_quality_ratio:.2f}x",
            f"FCF: {self.free_cash_flow:,.0f}",
        ]
        if self.auto_red_flags:
            lines += ["\nAuto-detected Red Flags:"] + [f"  ⚠ {f}" for f in self.auto_red_flags]
        if self.risk_level != "N/A":
            lines += [
                f"\nAI Risk Level: {self.risk_level}",
                f"Summary: {self.risk_summary}",
            ]
            if self.business_risks:
                lines += ["Business Risks:"] + [f"  • {r}" for r in self.business_risks]
            if self.mitigants:
                lines += ["Mitigants:"] + [f"  + {m}" for m in self.mitigants]
        return "\n".join(lines)


class RiskAgent:
    """Risk analysis agent."""

    def __init__(self, use_llm: bool = True) -> None:
        self._use_llm = use_llm
        self._engine = RatiosEngine()

    def analyse(self, symbol: str) -> RiskAnalysis:
        sym = symbol.strip().upper()
        log.info("RiskAgent: analysing %s", sym)

        df = self._engine.load(symbol=sym)
        if df.empty:
            raise DataNotFoundError(f"No fundamentals data for {sym}.")

        latest = df.sort_values("date").iloc[-1]
        sector = get_sector(sym)
        r = risk_score(latest)

        # Auto red flag detection
        flags = self._detect_flags(latest, df)

        result = RiskAnalysis(
            symbol=sym,
            sector=sector,
            latest_date=str(latest.get("date", ""))[:10],
            risk_score=r["score"],
            debt_to_equity=float(latest.get("debt_to_equity") or 0),
            earnings_quality_ratio=float(latest.get("earnings_quality_ratio") or 0),
            free_cash_flow=float(latest.get("free_cash_flow") or 0),
            net_income=float(latest.get("net_income") or 0),
            leverage_score=r["leverage_score"],
            fcf_cover_score=r["fcf_cover_score"],
            auto_red_flags=flags,
        )

        if self._use_llm:
            result = self._enrich_with_llm(result, latest)

        return result

    def _detect_flags(self, latest, df) -> list[str]:
        """Rule-based automatic red flag detection from quantitative data."""
        flags = []
        de = float(latest.get("debt_to_equity") or 0)
        fcf = float(latest.get("free_cash_flow") or 0)
        ni = float(latest.get("net_income") or 0)
        eq = float(latest.get("earnings_quality_ratio") or 0)
        roce = float(latest.get("roce_pct") or 0)

        if de > 2.0:
            flags.append(f"High leverage: Debt/Equity = {de:.2f}x (threshold: 2.0x)")
        if fcf < 0:
            flags.append("Negative free cash flow — company is consuming cash")
        if ni < 0:
            flags.append("Negative net income — loss-making")
        if 0 < eq < 0.5:
            flags.append(f"Low earnings quality: FCF/Net Income = {eq:.2f}x (healthy: >0.8x)")
        if roce < 8:
            flags.append(f"ROCE {roce:.1f}% is below typical cost of capital (8-10%)")

        # Multi-year trend: check if metrics are deteriorating
        sorted_df = df.sort_values("date")
        if len(sorted_df) >= 3:
            roe_trend = sorted_df["roe_pct"].dropna().tolist()
            if len(roe_trend) >= 3 and roe_trend[-1] < roe_trend[-3]:
                flags.append(
                    f"ROE declining over 3 years: "
                    f"{roe_trend[-3]:.1f}% → {roe_trend[-1]:.1f}%"
                )

        return flags

    def _enrich_with_llm(self, result: RiskAnalysis, latest) -> RiskAnalysis:
        try:
            from src.ai.rag import KnowledgeRetriever
            from src.ai.llm import LLMClient
            retriever = KnowledgeRetriever()
            client = LLMClient()
        except Exception as exc:
            log.warning("LLM/RAG init failed: %s", exc)
            return result

        # Pull red flags knowledge specifically
        context = retriever.get_context(
            f"common financial and governance red flags for {result.sector} companies",
            top_k=5, filter_source="common_red_flags.md",
        )
        if not context:
            context = retriever.get_context(
                f"financial risk assessment {result.sector}", top_k=4
            )

        metrics = (
            f"Symbol: {result.symbol} | Sector: {result.sector}\n"
            f"Risk Score: {result.risk_score}/100 | D/E: {result.debt_to_equity:.2f}x\n"
            f"FCF: {result.free_cash_flow:,.0f} | Net Income: {result.net_income:,.0f}\n"
            f"Earnings Quality (FCF/NI): {result.earnings_quality_ratio:.2f}x\n"
            f"Auto-detected flags: {result.auto_red_flags or 'None'}"
        )
        prompt = (
            f"Perform a risk assessment for this Indian listed stock:\n\n{metrics}\n\n"
            f"Identify: quantitative red flags from the data, governance concerns, "
            f"business risks, macro risks, overall risk level, "
            f"a brief risk summary, and key mitigants."
        )

        messages = client.build_messages(prompt, system_key="risk", context=context)
        try:
            out: _LLMRiskOutput = client.structured_chat(messages, _LLMRiskOutput)
            result.quantitative_red_flags = out.quantitative_red_flags
            result.governance_concerns    = out.governance_concerns
            result.business_risks         = out.business_risks
            result.macro_risks            = out.macro_risks
            result.risk_level             = out.risk_level
            result.risk_summary           = out.risk_summary
            result.mitigants              = out.mitigants
        except Exception as exc:
            log.warning("LLM risk analysis failed: %s", exc)
        return result

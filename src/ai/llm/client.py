"""client.py
-----------
LLM client wrapping LangChain's ChatOpenAI with:
  - Structured output via Pydantic models
  - Token counting
  - Retry on rate limit
  - Prompt template rendering

Usage
-----
    from src.ai.llm import LLMClient
    from pydantic import BaseModel

    class StockSummary(BaseModel):
        verdict: str
        reasoning: str
        risks: list[str]

    client = LLMClient()

    # Free-form
    reply = client.chat([
        {"role": "system", "content": "You are a stock analyst."},
        {"role": "user",   "content": "Analyse RELIANCE in 3 sentences."},
    ])

    # Structured output
    summary = client.structured_chat(messages, response_model=StockSummary)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from src.core.settings import settings
from src.core.exceptions import AgentError

log = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: dict[str, str] = {
    "analyst": (
        "You are an expert equity research analyst specialising in Indian stock markets (NSE). "
        "You reason from first principles, cite specific financial metrics, and always "
        "acknowledge uncertainty. You never give personal financial advice."
    ),
    "fundamental": (
        "You are a fundamental analysis expert. You evaluate businesses using metrics like "
        "ROE, ROCE, EPS growth, revenue CAGR, debt/equity, and free cash flow. "
        "You think like Warren Buffett and Peter Lynch."
    ),
    "technical": (
        "You are a technical analysis expert. You interpret price action, volume, momentum "
        "indicators (RSI, MACD), and support/resistance levels for NSE-listed stocks."
    ),
    "valuation": (
        "You are a valuation specialist. You use DCF, P/E band analysis, EV/EBITDA, "
        "and PEG ratios to determine intrinsic value and margin of safety for NSE stocks."
    ),
    "risk": (
        "You are a risk analyst. You identify accounting red flags, governance issues, "
        "balance sheet risks, and business model vulnerabilities in Indian listed companies."
    ),
    "cio": (
        "You are the Chief Investment Officer of an AI-powered Indian equity research firm. "
        "You synthesise fundamental, technical, valuation, and risk analyses into a single "
        "actionable investment recommendation: BUY, HOLD, or AVOID. "
        "You are concise, honest, and always quantify your conviction."
    ),
}


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class LLMClient:
    """Wrapper around OpenAI Chat Completions with helpers for agent workflows.

    Parameters
    ----------
    model:       OpenAI model name. Defaults to ``settings.openai_model``.
    temperature: Sampling temperature (0 = deterministic). Default 0.
    max_tokens:  Maximum tokens in the response.
    max_retries: Number of retries on rate-limit errors.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
        provider: Optional[str] = None,
    ) -> None:
        self._provider = (provider or settings.llm_provider).lower()
        self._temperature = temperature
        self._max_tokens = max_tokens or 3000   # reasoning models need headroom for CoT
        self._max_retries = max_retries

        # Resolve model name per provider
        if model:
            self._model = model
        elif self._provider == "deepseek":
            self._model = settings.deepseek_model
        elif self._provider == "ollama":
            self._model = settings.ollama_model
        else:
            self._model = settings.openai_model

        self._client = self._build_client()
        log.info("LLMClient: provider=%s  model=%s", self._provider, self._model)

    def _build_client(self):
        if self._provider == "watsonx":
            if not settings.watsonx_url or not settings.watsonx_project_id:
                raise AgentError(
                    "WATSONX_URL and WATSONX_PROJECT_ID must be set in .env"
                )
            return None   # watsonx uses its own httpx client (see chat())

        try:
            from openai import OpenAI
            import httpx
        except ImportError as exc:
            raise AgentError("openai package not installed. Run: pip install openai") from exc

        # Build an httpx client that respects the corporate proxy and
        # bypasses SSL verification (needed when the proxy re-signs certs).
        import os
        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        http_client = httpx.Client(
            proxy=proxy_url if proxy_url else None,
            verify=False,          # corporate proxy does SSL inspection
            timeout=60.0,
        )

        if self._provider == "deepseek":
            if not settings.deepseek_api_key:
                raise AgentError(
                    "DEEPSEEK_API_KEY is not set. Add it to your .env file.\n"
                    "Get a key at https://platform.deepseek.com"
                )
            return OpenAI(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com/v1",
                http_client=http_client,
            )

        if self._provider == "ollama":
            return OpenAI(
                api_key="ollama",
                base_url=f"{settings.ollama_base_url}/v1",
                http_client=http_client,
            )

        # openai (default)
        if not settings.openai_api_key:
            raise AgentError("OPENAI_API_KEY is not set. Add it to your .env file.")
        return OpenAI(api_key=settings.openai_api_key, http_client=http_client)

    # ------------------------------------------------------------------
    # Core completion
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
    ) -> str:
        """Send messages and return the assistant's reply as a string."""
        temp = temperature if temperature is not None else self._temperature

        # watsonx CPD path
        if self._provider == "watsonx":
            from src.ai.llm.watsonx_client import chat as _wx_chat
            for attempt in range(1, self._max_retries + 1):
                try:
                    return _wx_chat(messages, max_tokens=self._max_tokens, temperature=temp)
                except Exception as exc:
                    if attempt < self._max_retries:
                        wait = 2 ** attempt
                        log.warning("watsonx error, retrying in %ds: %s", wait, exc)
                        time.sleep(wait)
                    else:
                        raise AgentError(f"watsonx call failed: {exc}") from exc

        # openai / deepseek / ollama path
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temp,
                    max_tokens=self._max_tokens,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                if "rate_limit" in str(exc).lower() and attempt < self._max_retries:
                    wait = 2 ** attempt
                    log.warning("Rate limit hit — retrying in %ds (attempt %d/%d)", wait, attempt, self._max_retries)
                    time.sleep(wait)
                else:
                    raise AgentError(f"LLM call failed: {exc}") from exc
        raise AgentError("Max retries exceeded for LLM call")

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        response_model: Type[_T],
    ) -> _T:
        """Return the LLM response parsed into a Pydantic model.

        Uses OpenAI's JSON mode + Pydantic validation.
        Appends a schema instruction to the last user message automatically.
        """
        schema = response_model.model_json_schema()
        schema_instruction = (
            f"\n\nRespond ONLY with valid JSON matching this schema:\n{schema}"
        )
        # Append schema hint to last user message
        patched = list(messages)
        for i in range(len(patched) - 1, -1, -1):
            if patched[i]["role"] == "user":
                patched[i] = {
                    **patched[i],
                    "content": patched[i]["content"] + schema_instruction,
                }
                break

        raw = self.chat(patched)

        try:
            import json
            # Strip markdown code fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return response_model.model_validate(json.loads(raw))
        except Exception as exc:
            raise AgentError(
                f"Failed to parse LLM response into {response_model.__name__}: {exc}\nRaw: {raw}"
            ) from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def count_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken (falls back to word-count / 0.75)."""
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model(self._model)
            return len(enc.encode(text))
        except Exception:
            return int(len(text.split()) / 0.75)

    def build_messages(
        self,
        user_prompt: str,
        system_key: str = "analyst",
        context: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """Convenience builder for (system, [context], user) message lists.

        Parameters
        ----------
        user_prompt: The user's question or instruction.
        system_key:  Key from ``SYSTEM_PROMPTS`` dict.
        context:     Optional retrieved RAG context injected before the user prompt.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPTS.get(system_key, SYSTEM_PROMPTS["analyst"])}
        ]
        if context:
            messages.append({
                "role": "user",
                "content": f"Use the following reference knowledge when answering:\n\n{context}",
            })
            messages.append({"role": "assistant", "content": "Understood. I will use this knowledge."})
        messages.append({"role": "user", "content": user_prompt})
        return messages

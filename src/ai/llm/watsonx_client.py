"""
watsonx_client.py
-----------------
Client for IBM Cloud Pak for Data (CPD) watsonx.ai text/chat endpoint.

Auth flow (SSO / API key)
-------------------------
  POST {url}/icp4d-api/v1/authorize
  Body: {"username": "...", "api_key": "..."}
  Returns: {"token": "<bearer-jwt>"}

The Bearer token is cached and refreshed automatically before expiry.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from src.core.settings import settings

log = logging.getLogger(__name__)

_cached_token: str = ""
_token_expiry: float = 0.0


def _get_bearer_token() -> str:
    """Return a valid Bearer token, fetching a new one when expired."""
    global _cached_token, _token_expiry

    # Use static token if explicitly provided
    if settings.watsonx_token:
        return settings.watsonx_token

    if not settings.watsonx_username or not settings.watsonx_api_key:
        raise RuntimeError(
            "Set WATSONX_USERNAME + WATSONX_API_KEY (or WATSONX_TOKEN) in .env"
        )

    if _cached_token and time.time() < _token_expiry:
        return _cached_token

    log.info("Fetching CPD Bearer token for %s", settings.watsonx_username)
    auth_url = f"{settings.watsonx_url}/icp4d-api/v1/authorize"
    resp = httpx.post(
        auth_url,
        json={"username": settings.watsonx_username, "api_key": settings.watsonx_api_key},
        verify=False,
        timeout=20,
    )
    if not resp.is_success:
        raise RuntimeError(
            f"CPD auth failed ({resp.status_code}): {resp.text[:300]}"
        )
    data = resp.json()
    _cached_token = data.get("token") or data.get("access_token", "")
    if not _cached_token:
        raise RuntimeError(f"No token in CPD auth response: {data}")
    # CPD tokens expire in ~12 h; refresh 30 min early
    _token_expiry = time.time() + 11.5 * 3600
    log.info("CPD token acquired (expires in ~11.5 h)")
    return _cached_token


def chat(
    messages: list[dict[str, str]],
    max_tokens: int = 2000,
    temperature: float = 0.0,
) -> str:
    """POST to CPD /ml/v1/text/chat and return the reply string."""
    token = _get_bearer_token()

    payload: dict[str, Any] = {
        "messages":          messages,
        "project_id":        settings.watsonx_project_id,
        "model_id":          settings.watsonx_model,
        "max_tokens":        max_tokens,
        "temperature":       temperature,
        "frequency_penalty": 0,
        "presence_penalty":  0,
        "top_p":             1,
        "stop":              [],
    }

    def _call(tok: str) -> httpx.Response:
        return httpx.post(
            f"{settings.watsonx_url}/ml/v1/text/chat",
            params={"version": settings.watsonx_version},
            json=payload,
            headers={
                "Authorization": f"Bearer {tok}",
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            },
            verify=False,
            timeout=120,
        )

    resp = _call(token)

    # Token expired mid-session — refresh once and retry
    if resp.status_code == 401 and not settings.watsonx_token:
        global _cached_token, _token_expiry
        _cached_token = ""
        _token_expiry = 0.0
        token = _get_bearer_token()
        resp = _call(token)

    if not resp.is_success:
        raise RuntimeError(f"CPD chat failed ({resp.status_code}): {resp.text[:400]}")

    data = resp.json()
    try:
        choice = data["choices"][0]
        message = choice["message"]

        # Reasoning models (e.g. gpt-oss-120b) put chain-of-thought in
        # 'reasoning_content' and the final answer in 'content'.
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""

        if not content and reasoning:
            # Model ran out of tokens before writing 'content'.
            # Return what we can with a note.
            log.warning("Model produced only reasoning_content (finish_reason=%s) — max_tokens too low?",
                        choice.get('finish_reason'))
            # Extract the last paragraph of reasoning as a best-effort answer
            paragraphs = [p.strip() for p in reasoning.strip().split("\n\n") if p.strip()]
            excerpt = paragraphs[-1] if paragraphs else reasoning[-500:]
            return (
                "⚠️ The model ran out of tokens while reasoning. "
                "Partial reasoning:\n\n" + excerpt
            )

        if choice.get("finish_reason") == "length" and content:
            log.warning("Response truncated (finish_reason=length) — returning partial content")

        return content
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected CPD response: {data}") from exc


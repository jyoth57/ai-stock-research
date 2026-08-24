"""embedder.py
-------------
Thin wrapper around OpenAI's embedding API with local disk caching
so we never re-embed the same text twice.

Usage
-----
    from src.ai.embeddings import Embedder

    embedder = Embedder()
    vec = embedder.embed("What is ROCE?")
    vecs = embedder.embed_batch(["ROCE", "ROE", "Debt/Equity"])
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from src.core.settings import settings
from src.core.exceptions import EmbeddingError

log = logging.getLogger(__name__)

_CACHE_FILE = settings.processed_data_dir / "embedding_cache.json"


class Embedder:
    """Generate text embeddings via OpenAI with a JSON disk cache.

    Parameters
    ----------
    model:
        OpenAI embedding model. Defaults to ``settings.embedding_model``.
    cache_path:
        Path to the JSON cache file. Defaults to
        ``data/processed/embedding_cache.json``.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        cache_path: Optional[Path] = None,
    ) -> None:
        self._model = model or settings.embedding_model
        self._cache_path = cache_path or _CACHE_FILE
        self._cache: dict[str, list[float]] = self._load_cache()
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Client
    # ------------------------------------------------------------------

    def _build_client(self):
        try:
            from openai import OpenAI
            return OpenAI(api_key=settings.openai_api_key)
        except ImportError as exc:
            raise EmbeddingError(
                "openai package is not installed. Run: pip install openai"
            ) from exc

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _load_cache(self) -> dict[str, list[float]]:
        if self._cache_path.exists():
            try:
                return json.loads(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                log.warning("Embedding cache corrupted \u2014 starting fresh")
        return {}

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _cache_key(text: str, model: str) -> str:
        return hashlib.sha256(f"{model}::{text}".encode()).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string.

        Results are cached on disk so identical texts are never re-embedded.
        """
        key = self._cache_key(text, self._model)
        if key in self._cache:
            return self._cache[key]

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=[text],
            )
            vector: list[float] = response.data[0].embedding
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc

        self._cache[key] = vector
        self._save_cache()
        return vector

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """Embed a list of texts, using cache where possible.

        Parameters
        ----------
        texts:      List of strings to embed.
        batch_size: Maximum texts per API call (OpenAI limit: 2048).

        Returns
        -------
        list[list[float]]
            Embedding vectors in the same order as *texts*.
        """
        results: list[list[float] | None] = [None] * len(texts)
        to_embed: list[tuple[int, str]] = []

        # Check cache first
        for i, text in enumerate(texts):
            key = self._cache_key(text, self._model)
            if key in self._cache:
                results[i] = self._cache[key]
            else:
                to_embed.append((i, text))

        # Batch-embed cache misses
        if to_embed:
            log.info("Embedding %d new texts via OpenAI\u2026", len(to_embed))
            for chunk_start in range(0, len(to_embed), batch_size):
                chunk = to_embed[chunk_start: chunk_start + batch_size]
                batch_texts = [t for _, t in chunk]
                try:
                    response = self._client.embeddings.create(
                        model=self._model,
                        input=batch_texts,
                    )
                except Exception as exc:
                    raise EmbeddingError(f"Batch embedding failed: {exc}") from exc

                for j, (original_idx, text) in enumerate(chunk):
                    vec = response.data[j].embedding
                    key = self._cache_key(text, self._model)
                    self._cache[key] = vec
                    results[original_idx] = vec

            self._save_cache()
            log.info("Embedding complete. Cache now has %d entries.", len(self._cache))

        return results  # type: ignore[return-value]

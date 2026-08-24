"""retriever.py
--------------
Queries the ChromaDB knowledge index and returns formatted context
ready to be injected into LLM prompts.

Usage
-----
    from src.ai.rag import KnowledgeRetriever

    retriever = KnowledgeRetriever()

    # Simple retrieval
    chunks = retriever.retrieve("What valuation method should I use for a bank?")

    # Get a formatted context string ready for an LLM prompt
    context = retriever.get_context("How do I identify accounting red flags?")
    print(context)

    # Targeted: retrieve only from specific knowledge files
    context = retriever.get_context(
        "what makes a wide moat?",
        filter_source="buffett_principles.md",
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.core.settings import settings
from src.core.exceptions import RAGError

log = logging.getLogger(__name__)

_COLLECTION_NAME = "ai_stock_knowledge"


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_file: str
    section: str
    text: str
    score: float   # cosine similarity (0–1, higher = more relevant)

    def __str__(self) -> str:
        return (
            f"[{self.source_file} \u2192 {self.section}] (score: {self.score:.3f})\n"
            f"{self.text}"
        )


class KnowledgeRetriever:
    """Query the ChromaDB knowledge index for relevant context.

    Parameters
    ----------
    chroma_dir:      ChromaDB persistence directory.
    collection_name: Name of the ChromaDB collection.
    top_k:           Default number of chunks to return per query.
    """

    def __init__(
        self,
        chroma_dir=None,
        collection_name: str = _COLLECTION_NAME,
        top_k: int = 5,
    ) -> None:
        self._chroma_dir = chroma_dir or settings.chroma_persist_dir
        self._collection_name = collection_name
        self._default_top_k = top_k
        self._collection = self._get_collection()

    def _get_collection(self):
        try:
            import chromadb
        except ImportError as exc:
            raise RAGError(
                "chromadb is not installed. Run: pip install chromadb"
            ) from exc

        client = chromadb.PersistentClient(path=str(self._chroma_dir))
        try:
            return client.get_collection(name=self._collection_name)
        except Exception as exc:
            raise RAGError(
                f"Knowledge index not found (collection: {self._collection_name}). "
                "Run KnowledgeIndexer().index() first."
            ) from exc

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_source: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        """Return the top-k most relevant chunks for *query*.

        Parameters
        ----------
        query:         Natural language question or topic.
        top_k:         Number of chunks to return. Overrides instance default.
        filter_source: Restrict to a specific knowledge file, e.g.
                       ``"buffett_principles.md"``.

        Returns
        -------
        list[RetrievedChunk]
            Sorted by descending relevance score.
        """
        from src.ai.embeddings import Embedder

        k = top_k or self._default_top_k

        try:
            query_vec = Embedder().embed(query)
        except Exception as exc:
            raise RAGError(f"Failed to embed query: {exc}") from exc

        where = {"source_file": filter_source} if filter_source else None

        try:
            results = self._collection.query(
                query_embeddings=[query_vec],
                n_results=min(k, self._collection.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise RAGError(f"ChromaDB query failed: {exc}") from exc

        chunks: list[RetrievedChunk] = []
        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            score = max(0.0, 1.0 - dist)   # convert cosine distance → similarity
            chunks.append(RetrievedChunk(
                chunk_id=results["ids"][0][i],
                source_file=meta.get("source_file", ""),
                section=meta.get("section", ""),
                text=doc,
                score=score,
            ))

        return sorted(chunks, key=lambda c: c.score, reverse=True)

    def get_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_source: Optional[str] = None,
        min_score: float = 0.30,
        separator: str = "\n\n---\n\n",
    ) -> str:
        """Return a formatted context string ready to inject into an LLM prompt.

        Chunks below *min_score* are excluded. Returns an empty string if
        the index is empty or no relevant chunks are found.

        Parameters
        ----------
        query:         Natural language query.
        top_k:         Max chunks to include.
        filter_source: Restrict to a specific knowledge file.
        min_score:     Minimum cosine similarity threshold (0–1).
        separator:     String inserted between chunks.
        """
        try:
            chunks = self.retrieve(query, top_k=top_k, filter_source=filter_source)
        except RAGError as exc:
            log.warning("RAG retrieval failed: %s", exc)
            return ""

        relevant = [c for c in chunks if c.score >= min_score]
        if not relevant:
            log.debug("No chunks above min_score=%.2f for query: %s", min_score, query[:60])
            return ""

        parts = []
        for chunk in relevant:
            parts.append(
                f"**Source:** {chunk.source_file} | **Section:** {chunk.section}\n\n"
                f"{chunk.text}"
            )

        header = f"[Knowledge Base — {len(parts)} relevant excerpt(s) for: \"{query[:80]}\"]\n\n"
        return header + separator.join(parts)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def collection_size(self) -> int:
        return self._collection.count()

    def list_sources(self) -> list[str]:
        """Return unique source filenames currently indexed."""
        result = self._collection.get(include=["metadatas"])
        sources = {m.get("source_file", "") for m in result["metadatas"]}
        return sorted(s for s in sources if s)

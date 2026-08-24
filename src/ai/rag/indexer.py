"""indexer.py
------------
Indexes all Markdown files in knowledge/ into a ChromaDB vector store.

Each document is chunked by top-level headings (## sections).
Metadata stored per chunk: source file, section title, char offset.

Usage
-----
    from src.ai.rag import KnowledgeIndexer

    indexer = KnowledgeIndexer()
    indexer.index()           # indexes all knowledge/*.md
    indexer.index(force=True) # re-index even unchanged files
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.settings import settings
from src.core.exceptions import RAGError, EmbeddingError

log = logging.getLogger(__name__)

_COLLECTION_NAME = "ai_stock_knowledge"
_HASH_STORE = settings.processed_data_dir / "knowledge_index_hashes.json"


@dataclass
class DocumentChunk:
    chunk_id: str
    source_file: str
    section: str
    text: str
    embedding: Optional[list[float]] = None


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

def _chunk_markdown(text: str, source_file: str) -> list[DocumentChunk]:
    """Split a Markdown document into chunks at ## headings."""
    # Split on lines starting with ## (section level)
    pattern = re.compile(r"^##+ .+", re.MULTILINE)
    positions = [m.start() for m in pattern.finditer(text)]
    positions.append(len(text))  # sentinel

    chunks: list[DocumentChunk] = []

    # Preamble before the first heading (file intro / H1)
    if positions[0] > 0:
        preamble = text[: positions[0]].strip()
        if preamble:
            chunk_id = hashlib.md5(f"{source_file}::preamble".encode()).hexdigest()
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                source_file=source_file,
                section="Introduction",
                text=preamble,
            ))

    for i in range(len(positions) - 1):
        section_text = text[positions[i]: positions[i + 1]].strip()
        if not section_text:
            continue

        # First line is the heading
        lines = section_text.splitlines()
        section_title = lines[0].lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()

        if not body:
            continue

        chunk_id = hashlib.md5(f"{source_file}::{section_title}".encode()).hexdigest()
        chunks.append(DocumentChunk(
            chunk_id=chunk_id,
            source_file=source_file,
            section=section_title,
            text=f"{section_title}\n\n{body}",
        ))

    return chunks


# ---------------------------------------------------------------------------
# KnowledgeIndexer
# ---------------------------------------------------------------------------

class KnowledgeIndexer:
    """Index the knowledge/ directory into ChromaDB.

    Parameters
    ----------
    knowledge_dir:   Directory containing ``*.md`` knowledge files.
    chroma_dir:      ChromaDB persistence directory.
    collection_name: Name of the ChromaDB collection.
    """

    def __init__(
        self,
        knowledge_dir: Optional[Path] = None,
        chroma_dir: Optional[Path] = None,
        collection_name: str = _COLLECTION_NAME,
    ) -> None:
        self._knowledge_dir = knowledge_dir or settings.knowledge_dir
        self._chroma_dir = chroma_dir or settings.chroma_persist_dir
        self._collection_name = collection_name
        self._collection = self._get_collection()

    def _get_collection(self):
        try:
            import chromadb
        except ImportError as exc:
            raise RAGError(
                "chromadb is not installed. Run: pip install chromadb"
            ) from exc

        self._chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self._chroma_dir))
        return client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Hash-based change detection
    # ------------------------------------------------------------------

    def _load_hashes(self) -> dict[str, str]:
        import json
        if _HASH_STORE.exists():
            try:
                return json.loads(_HASH_STORE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_hashes(self, hashes: dict[str, str]) -> None:
        import json
        _HASH_STORE.parent.mkdir(parents=True, exist_ok=True)
        _HASH_STORE.write_text(json.dumps(hashes, indent=2), encoding="utf-8")

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def index(self, force: bool = False) -> dict[str, int]:
        """Index all Markdown files in the knowledge directory.

        Parameters
        ----------
        force: Re-index all files even if unchanged.

        Returns
        -------
        dict[str, int]
            ``{filename: chunks_indexed}`` for each file processed.
        """
        from src.ai.embeddings import Embedder

        md_files = sorted(self._knowledge_dir.glob("*.md"))
        if not md_files:
            log.warning("No .md files found in %s", self._knowledge_dir)
            return {}

        embedder = Embedder()
        hashes = self._load_hashes()
        summary: dict[str, int] = {}

        for md_path in md_files:
            file_hash = self._file_hash(md_path)
            if not force and hashes.get(md_path.name) == file_hash:
                log.info("Skipping %s (unchanged)", md_path.name)
                summary[md_path.name] = 0
                continue

            log.info("Indexing %s \u2026", md_path.name)
            text = md_path.read_text(encoding="utf-8")
            chunks = _chunk_markdown(text, source_file=md_path.name)

            if not chunks:
                log.warning("No chunks extracted from %s", md_path.name)
                continue

            # Delete stale chunks for this file before re-inserting
            existing = self._collection.get(
                where={"source_file": md_path.name}
            )
            if existing["ids"]:
                self._collection.delete(ids=existing["ids"])

            # Embed all chunks in one batch
            texts = [c.text for c in chunks]
            vectors = embedder.embed_batch(texts)

            self._collection.add(
                ids=[c.chunk_id for c in chunks],
                embeddings=vectors,
                documents=texts,
                metadatas=[
                    {"source_file": c.source_file, "section": c.section}
                    for c in chunks
                ],
            )

            hashes[md_path.name] = file_hash
            summary[md_path.name] = len(chunks)
            log.info("Indexed %d chunks from %s", len(chunks), md_path.name)

        self._save_hashes(hashes)
        total = sum(summary.values())
        log.info("Indexing complete. %d chunks across %d files.", total, len(summary))
        return summary

    def collection_size(self) -> int:
        """Return the total number of chunks in the collection."""
        return self._collection.count()

    def reset(self) -> None:
        """Delete all indexed chunks and reset the hash store."""
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(self._chroma_dir))
            client.delete_collection(self._collection_name)
            self._collection = client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            if _HASH_STORE.exists():
                _HASH_STORE.unlink()
            log.info("Knowledge index reset.")
        except Exception as exc:
            raise RAGError(f"Failed to reset collection: {exc}") from exc

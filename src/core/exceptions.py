"""Typed exception hierarchy for AI Stock Research.

All project exceptions inherit from AIStockResearchError so callers
can catch the entire family with a single except clause.
"""


class AIStockResearchError(Exception):
    """Base exception for all project errors."""


# ── Data layer ────────────────────────────────────────────────────────────────

class DataNotFoundError(AIStockResearchError):
    """Requested data does not exist locally or remotely."""


class DataValidationError(AIStockResearchError):
    """Downloaded or loaded data failed quality checks.

    Attach a list of ValidationIssue objects as the 'issues' attribute.
    """
    def __init__(self, message: str, issues: list | None = None) -> None:
        super().__init__(message)
        self.issues = issues or []


class DownloadError(AIStockResearchError):
    """Failed to fetch data from an external source."""


class InsufficientDataError(AIStockResearchError):
    """Not enough data points to compute the requested metric."""


# ── Database layer ────────────────────────────────────────────────────────────

class DatabaseError(AIStockResearchError):
    """Database connection or query failure."""


# ── Configuration ─────────────────────────────────────────────────────────────

class ConfigurationError(AIStockResearchError):
    """Missing or invalid application configuration."""


# ── Analytics / Valuation ─────────────────────────────────────────────────────

class ValuationError(AIStockResearchError):
    """Cannot compute valuation due to missing or invalid inputs."""


class ScreenerError(AIStockResearchError):
    """Stock screener encountered an invalid rule or filter."""


# ── AI / Agent layer ──────────────────────────────────────────────────────────

class AgentError(AIStockResearchError):
    """LLM agent returned an unexpected or unusable response."""


class EmbeddingError(AIStockResearchError):
    """Failed to generate or retrieve text embeddings."""


class RAGError(AIStockResearchError):
    """Knowledge base retrieval failure."""

"""Backwards-compatibility shim — delegates to DuckDBStore.
All API code should import get_store() directly from duckdb_store."""
from src.database.duckdb_store import get_store  # noqa: F401


def get_scan(**kwargs):
    """Return signals DataFrame from DuckDB (replaces old run_scan cache)."""
    return get_store().get_signals(**kwargs)

"""Sector and industry helpers for NSE symbols.

The primary SECTOR_MAP is maintained in src/core/constants.py.
This module provides the query interface used by analytics and agents.
"""

from __future__ import annotations

from src.core.constants import SECTOR_MAP, get_symbols_by_sector


def get_sector(symbol: str) -> str:
    """Return the broad sector for a bare NSE symbol.

    Returns ``'Unknown'`` if the symbol is not in the map.

    >>> get_sector("TCS")
    'IT'
    >>> get_sector("HDFCBANK")
    'Banking'
    """
    return SECTOR_MAP.get(symbol.strip().upper(), "Unknown")


def get_symbols_for_sector(sector: str) -> list[str]:
    """Return all known symbols for a given sector name.

    Case-insensitive match.

    >>> get_symbols_for_sector("IT")
    ['TCS', 'INFY', ...]
    """
    sector_lower = sector.strip().lower()
    return [
        sym
        for sec, syms in get_symbols_by_sector().items()
        for sym in syms
        if sec.lower() == sector_lower
    ]


def all_sectors() -> list[str]:
    """Return a sorted list of all distinct sector names."""
    return sorted(get_symbols_by_sector().keys())


def sector_summary() -> dict[str, int]:
    """Return {sector: symbol_count} for all sectors."""
    return {
        sec: len(syms)
        for sec, syms in sorted(get_symbols_by_sector().items())
    }

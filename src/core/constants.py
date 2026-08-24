"""Project-wide constants — index constituents, sector maps, column names."""

from __future__ import annotations

# ── NSE ticker suffix ─────────────────────────────────────────────────────────
NSE_SUFFIX = ".NS"

# ── OHLCV column names ────────────────────────────────────────────────────────
OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
DATE_COL = "Date"

# ── Index constituents (bare symbols, no .NS) ─────────────────────────────────
NIFTY_50: list[str] = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

NIFTY_NEXT_50: list[str] = [
    "ABB", "ADANIGREEN", "ADANITRANS", "AMBUJACEM", "ATGL",
    "BANKBARODA", "BERGEPAINT", "BOSCHLTD", "CANBK", "CHOLAFIN",
    "COLPAL", "DMART", "DIVISLAB", "DLF", "GAIL",
    "GODREJCP", "HAVELLS", "INDHOTEL", "INDUSTOWER", "IRCTC",
    "JINDALSTEL", "JUBLFOOD", "LICI", "LODHA", "LTIM",
    "LTTS", "LUPIN", "MCDOWELL-N", "MUTHOOTFIN", "NAUKRI",
    "NHPC", "NMDC", "OFSS", "PAGEIND", "PIDILITIND",
    "PIIND", "POLYCAB", "RECLTD", "SBICARD", "SIEMENS",
    "SUNDARMFIN", "TATAPOWER", "TORNTPHARM", "TVSMOTOR", "UBL",
    "UNIONBANK", "UPL", "VEDL", "VOLTAS", "ZOMATO",
]

# ── Sector map (symbol → broad sector) ────────────────────────────────────────
SECTOR_MAP: dict[str, str] = {
    # Banking & Financial Services
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking",
    "KOTAKBANK": "Banking", "AXISBANK": "Banking", "INDUSINDBK": "Banking",
    "BANKBARODA": "Banking", "CANBK": "Banking", "UNIONBANK": "Banking",
    "BAJFINANCE": "NBFC", "BAJAJFINSV": "NBFC", "CHOLAFIN": "NBFC",
    "MUTHOOTFIN": "NBFC", "SUNDARMFIN": "NBFC", "SHRIRAMFIN": "NBFC",
    "SBICARD": "NBFC", "HDFCLIFE": "Insurance", "SBILIFE": "Insurance", "LICI": "Insurance",
    # IT Services
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "LTIM": "IT", "LTTS": "IT", "OFSS": "IT", "NAUKRI": "IT",
    # FMCG
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "COLPAL": "FMCG", "GODREJCP": "FMCG",
    "TATACONSUM": "FMCG", "MCDOWELL-N": "FMCG", "UBL": "FMCG",
    # Pharma
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "DIVISLAB": "Pharma", "LUPIN": "Pharma", "TORNTPHARM": "Pharma", "PIIND": "Pharma",
    # Auto & Ancillaries
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto",
    "BAJAJ-AUTO": "Auto", "HEROMOTOCO": "Auto", "EICHERMOT": "Auto",
    "TVSMOTOR": "Auto", "BOSCHLTD": "Auto Ancillary",
    # Consumer / Retail
    "ASIANPAINT": "Consumer", "BERGEPAINT": "Consumer", "PIDILITIND": "Consumer",
    "TITAN": "Consumer", "HAVELLS": "Consumer", "VOLTAS": "Consumer",
    "PAGEIND": "Consumer", "DMART": "Retail", "TRENT": "Retail",
    "JUBLFOOD": "QSR", "INDHOTEL": "Hospitality",
    # Infrastructure / Capital Goods
    "LT": "Infra", "ADANIPORTS": "Infra", "SIEMENS": "Capital Goods",
    "ABB": "Capital Goods", "BEL": "Defence", "INDUSTOWER": "Telecom Infra",
    "TATAPOWER": "Power", "NHPC": "Power", "POWERGRID": "Power",
    "NTPC": "Power", "ADANIGREEN": "Renewables", "ADANITRANS": "Power",
    "RECLTD": "Power Finance",
    # Metals & Mining
    "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "HINDALCO": "Metals",
    "VEDL": "Metals", "COALINDIA": "Mining", "NMDC": "Mining",
    "JINDALSTEL": "Metals",
    # Energy
    "RELIANCE": "Energy", "ONGC": "Oil & Gas", "BPCL": "Oil & Gas",
    "GAIL": "Oil & Gas", "ATGL": "Gas Distribution",
    # Chemicals
    "UPL": "Agrochemicals",
    # Real Estate
    "DLF": "Real Estate", "LODHA": "Real Estate",
    # Telecom
    "BHARTIARTL": "Telecom",
    # Cement
    "ULTRACEMCO": "Cement", "GRASIM": "Cement", "AMBUJACEM": "Cement",
    # Diversified
    "IRCTC": "Travel", "ZOMATO": "Food Tech", "POLYCAB": "Wires & Cables",
}

# ── Sector → list of symbols (inverse of SECTOR_MAP) ─────────────────────────
_SYMBOLS_BY_SECTOR: dict[str, list[str]] | None = None


def get_symbols_by_sector() -> dict[str, list[str]]:
    """Return {sector: [symbols]} built lazily from SECTOR_MAP."""
    global _SYMBOLS_BY_SECTOR
    if _SYMBOLS_BY_SECTOR is None:
        result: dict[str, list[str]] = {}
        for sym, sector in SECTOR_MAP.items():
            result.setdefault(sector, []).append(sym)
        _SYMBOLS_BY_SECTOR = result
    return _SYMBOLS_BY_SECTOR


# ── Fundamental metric display names ─────────────────────────────────────────
METRIC_LABELS: dict[str, str] = {
    "roe_pct": "ROE (%)",
    "roce_pct": "ROCE (%)",
    "eps_growth_pct": "EPS Growth (%)",
    "revenue_cagr_pct": "Revenue CAGR (%)",
    "debt_to_equity": "Debt / Equity",
    "free_cash_flow": "Free Cash Flow",
}

# ── Scoring weights ───────────────────────────────────────────────────────────
SCORING_WEIGHTS: dict[str, float] = {
    "quality": 0.30,
    "growth": 0.25,
    "valuation": 0.25,
    "technical": 0.10,
    "risk": 0.10,
}

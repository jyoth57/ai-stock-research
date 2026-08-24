"""
download_sector_map.py
----------------------
Downloads NSE sector-index constituent lists and builds a
SYMBOL → SECTOR mapping saved to:
  - data/raw/sector_map.csv
  - DuckDB table: sector_map

Then rebuilds the DuckDB signals table with sector info joined in.

Run:
    python -m scripts.download_sector_map
"""

from __future__ import annotations

import logging
import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.duckdb_store import get_store, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.nseindia.com/",
}

# NSE sector index → friendly label
SECTOR_INDICES = {
    "ind_niftyauto_list.csv":              "Auto",
    "ind_niftybank_list.csv":              "Banking",
    "ind_niftypsubank_list.csv":           "PSU Banks",
    "ind_niftyfinancialservices_list.csv": "Financial Services",
    "ind_niftyfmcg_list.csv":             "FMCG",
    "ind_niftyit_list.csv":               "IT",
    "ind_niftymedia_list.csv":            "Media",
    "ind_niftymetal_list.csv":            "Metal",
    "ind_niftypharma_list.csv":           "Pharma",
    "ind_niftyhealthcare_list.csv":       "Healthcare",
    "ind_niftyrealty_list.csv":           "Realty",
    "ind_niftyenergy_list.csv":           "Energy",
    "ind_niftyoilgas_list.csv":           "Oil & Gas",
    "ind_niftyinfra_list.csv":            "Infrastructure",
    "ind_niftyconsumerDurables_list.csv": "Consumer Durables",
    "ind_niftycpse_list.csv":             "PSU",
    "ind_niftydefence_list.csv":          "Defence",
    "ind_niftyindia_mfg_list.csv":        "Manufacturing",
}

BASE_URL = "https://nsearchives.nseindia.com/content/indices/"

# Fallback: hardcoded sector mapping for ~200 major NSE stocks
# Used when the NSE download fails (e.g. network restrictions)
FALLBACK_MAPPING = {
    # ── IT & Technology ──────────────────────────────────────────────────────
    "TCS":"IT","INFY":"IT","WIPRO":"IT","HCLTECH":"IT","TECHM":"IT",
    "LTIM":"IT","MPHASIS":"IT","COFORGE":"IT","PERSISTENT":"IT","OFSS":"IT",
    "CYIENT":"IT","KPITTECH":"IT","LTTS":"IT","NIIT":"IT","HEXAWARE":"IT",
    "ZENSAR":"IT","MASTEK":"IT","TATAELXSI":"IT","HAPPSTMNDS":"IT","RATEGAIN":"IT",
    "NETWEB":"IT","NEWGEN":"IT","NUCLEUS":"IT","TANLA":"IT","INTELLECT":"IT",
    "ROUTE":"IT","AURIONPRO":"IT","SAKSOFT":"IT","CYIENTDLM":"IT","SONACOMS":"IT",
    # ── Banking ──────────────────────────────────────────────────────────────
    "HDFCBANK":"Banking","ICICIBANK":"Banking","SBIN":"Banking","KOTAKBANK":"Banking",
    "AXISBANK":"Banking","INDUSINDBK":"Banking","BANDHANBNK":"Banking","IDFCFIRSTB":"Banking",
    "FEDERALBNK":"Banking","RBLBANK":"Banking","AUBANK":"Banking","CSBBANK":"Banking",
    "DCBBANK":"Banking","KARNATAKA":"Banking","NAINITAL":"Banking","JKBANK":"Banking",
    "SOUTHBANK":"Banking","CITYUNIONBANK":"Banking","LAKSHVILAS":"Banking",
    # ── PSU Banks ────────────────────────────────────────────────────────────
    "BANKBARODA":"PSU Banks","PNB":"PSU Banks","CANBK":"PSU Banks","UNIONBANK":"PSU Banks",
    "INDIANB":"PSU Banks","MAHABANK":"PSU Banks","IOB":"PSU Banks","BANKINDIA":"PSU Banks",
    "UCOBANK":"PSU Banks","CENTRALBK":"PSU Banks","PSBBANK":"PSU Banks",
    # ── Financial Services ───────────────────────────────────────────────────
    "BAJFINANCE":"Financial Services","BAJAJFINSV":"Financial Services",
    "SBILIFE":"Financial Services","HDFCLIFE":"Financial Services",
    "ICICIGI":"Financial Services","MUTHOOTFIN":"Financial Services",
    "CHOLAFIN":"Financial Services","LICHSGFIN":"Financial Services",
    "POONAWALLA":"Financial Services","M&MFIN":"Financial Services",
    "MANAPPURAM":"Financial Services","SHRIRAMFIN":"Financial Services",
    "HDFC":"Financial Services","LICI":"Financial Services","GICRE":"Financial Services",
    "NIACL":"Financial Services","ICICIPRULI":"Financial Services",
    "AAVAS":"Financial Services","CANFINHOME":"Financial Services",
    "HOMEFIRST":"Financial Services","REPCO":"Financial Services",
    "APTUS":"Financial Services","CREDITACC":"Financial Services",
    "SBICARD":"Financial Services","STARHEALTH":"Financial Services",
    # ── FMCG ─────────────────────────────────────────────────────────────────
    "HINDUNILVR":"FMCG","ITC":"FMCG","NESTLEIND":"FMCG","BRITANNIA":"FMCG",
    "DABUR":"FMCG","MARICO":"FMCG","GODREJCP":"FMCG","EMAMILTD":"FMCG",
    "COLPAL":"FMCG","TATACONSUM":"FMCG","VBL":"FMCG","RADICO":"FMCG",
    "BIKAJI":"FMCG","PATANJALI":"FMCG","JYOTHYLAB":"FMCG","ZYDUSWELL":"FMCG",
    "HATSUN":"FMCG","PARAS":"FMCG","VARUNBEV":"FMCG","GODFRYPHLP":"FMCG",
    "VST":"FMCG","GILLETTE":"FMCG","PGHH":"FMCG","KANSAINER":"FMCG",
    # ── Auto & Auto Components ───────────────────────────────────────────────
    "MARUTI":"Auto","TATAMOTORS":"Auto","M&M":"Auto","BAJAJ-AUTO":"Auto",
    "HEROMOTOCO":"Auto","EICHERMOT":"Auto","TVSMOTOR":"Auto","ASHOKLEY":"Auto",
    "MOTHERSON":"Auto","BOSCHLTD":"Auto","BALKRISIND":"Auto","MRF":"Auto",
    "APOLLOTYRE":"Auto","CEAT":"Auto","JKTYRE":"Auto","SCHAEFFLER":"Auto",
    "TIINDIA":"Auto","EXIDEIND":"Auto","AMARARAJA":"Auto","SUNDRM":"Auto",
    "ENDURANCE":"Auto","GABRIEL":"Auto","SUPRAJIT":"Auto","MINDAIND":"Auto",
    "LUMAX":"Auto","SUBROS":"Auto","JAMNA":"Auto","SUNDRMFAST":"Auto",
    "CRAFTSMAN":"Auto","SANDHAR":"Auto","BORORENEW":"Auto",
    # ── Pharma ───────────────────────────────────────────────────────────────
    "SUNPHARMA":"Pharma","DRREDDY":"Pharma","CIPLA":"Pharma","DIVISLAB":"Pharma",
    "TORNTPHARM":"Pharma","ALKEM":"Pharma","LUPIN":"Pharma","AUROPHARMA":"Pharma",
    "BIOCON":"Pharma","IPCALAB":"Pharma","GRANULES":"Pharma","ABBOTINDIA":"Pharma",
    "PFIZER":"Pharma","SANOFI":"Pharma","GLAXO":"Pharma","AJANTPHARM":"Pharma",
    "LAURUSLABS":"Pharma","NATCOPHARM":"Pharma","SUVEN":"Pharma","GLENMARK":"Pharma",
    "IIFL":"Pharma","MANKIND":"Pharma","JBCHEPHARM":"Pharma","FDC":"Pharma",
    "ERIS":"Pharma","SOLARA":"Pharma","STRIDES":"Pharma","NECTAR":"Pharma",
    # ── Healthcare ───────────────────────────────────────────────────────────
    "APOLLOHOSP":"Healthcare","FORTIS":"Healthcare","MAXHEALTH":"Healthcare",
    "MEDANTA":"Healthcare","KIMS":"Healthcare","NH":"Healthcare",
    "RAINBOW":"Healthcare","METROPOLIS":"Healthcare","THYROCARE":"Healthcare",
    "DRLA":"Healthcare","VIJAYA":"Healthcare","HEALTHIUMS":"Healthcare",
    "POLYMED":"Healthcare","LAXMI":"Healthcare","SHALBY":"Healthcare",
    # ── Energy & Oil & Gas ───────────────────────────────────────────────────
    "RELIANCE":"Energy","ONGC":"Oil & Gas","BPCL":"Oil & Gas","IOC":"Oil & Gas",
    "HINDPETRO":"Oil & Gas","GAIL":"Oil & Gas","OIL":"Oil & Gas","MGL":"Oil & Gas",
    "IGL":"Oil & Gas","PETRONET":"Oil & Gas","MRPL":"Oil & Gas","CPCL":"Oil & Gas",
    "GUJGASLTD":"Oil & Gas","AEGAS":"Oil & Gas","ATGL":"Oil & Gas",
    # ── Power ────────────────────────────────────────────────────────────────
    "NTPC":"Power","POWERGRID":"Power","ADANIGREEN":"Power","TATAPOWER":"Power",
    "CESC":"Power","TORNTPOWER":"Power","NHPC":"Power","SJVN":"Power",
    "JSWENERGY":"Power","RPOWER":"Power","NPCIL":"Power","JPPOWER":"Power",
    "GETPOWER":"Power","CESC":"Power","INOXGREEN":"Power","INOXWIND":"Power",
    # ── Renewable Energy ─────────────────────────────────────────────────────
    "ADANIGREEN":"Renewable Energy","SUZLON":"Renewable Energy","INOXWIND":"Renewable Energy",
    "WEBSOL":"Renewable Energy","GOLDENERGY":"Renewable Energy",
    "JSWEL":"Renewable Energy","GREENKO":"Renewable Energy",
    # ── Metal & Mining ───────────────────────────────────────────────────────
    "TATASTEEL":"Metal","JSWSTEEL":"Metal","HINDALCO":"Metal","VEDL":"Metal",
    "SAIL":"Metal","NMDC":"Metal","NATIONALUM":"Metal","COALINDIA":"Metal",
    "HINDCOPPER":"Metal","APLAPOLLO":"Metal","RATNAMANI":"Metal","JINDALSAW":"Metal",
    "WELSPUNLIV":"Metal","KALYANKJIL":"Metal","JSWHL":"Metal","MOIL":"Metal",
    "GRAVITA":"Metal","HINDUSTAN":"Metal","NRAIL":"Metal",
    # ── Capital Goods & Engineering ──────────────────────────────────────────
    "LT":"Capital Goods","SIEMENS":"Capital Goods","ABB":"Capital Goods",
    "BHEL":"Capital Goods","CUMMINSIND":"Capital Goods","HAVELLS":"Capital Goods",
    "POLYCAB":"Capital Goods","KEC":"Capital Goods","KALPATPOWR":"Capital Goods",
    "THERMAX":"Capital Goods","AIAENG":"Capital Goods","ELGIEQUIP":"Capital Goods",
    "GRINDWELL":"Capital Goods","TIMKEN":"Capital Goods","SKF":"Capital Goods",
    "ISGEC":"Capital Goods","PRAJ":"Capital Goods","WAAREEENER":"Capital Goods",
    "PREMIER":"Capital Goods","STOVEKRAFT":"Capital Goods","TRIL":"Capital Goods",
    # ── Infrastructure ───────────────────────────────────────────────────────
    "ADANIPORTS":"Infrastructure","ULTRACEMCO":"Infrastructure",
    "SHREECEM":"Infrastructure","ACC":"Infrastructure","AMBUJACEMENT":"Infrastructure",
    "DALMIACEMT":"Infrastructure","NUVOCO":"Infrastructure","HEIDELBERG":"Infrastructure",
    "JKCEMENT":"Infrastructure","RAMCOCEM":"Infrastructure","BIRLACORPN":"Infrastructure",
    "IRCON":"Infrastructure","NCC":"Infrastructure","HG INFRA":"Infrastructure",
    "NBCC":"Infrastructure","PNC":"Infrastructure","HGINFRA":"Infrastructure",
    "PATEL":"Infrastructure","AHLADA":"Infrastructure",
    # ── Defence ──────────────────────────────────────────────────────────────
    "BEL":"Defence","HAL":"Defence","DATAPATTNS":"Defence","MAZDOCK":"Defence",
    "COCHINSHIP":"Defence","GRSE":"Defence","BEML":"Defence","MTAR":"Defence",
    "BHARAT":"Defence","PARAS":"Defence","PREMIER":"Defence","IDEA":"Defence",
    "DYNAMATECH":"Defence","AVANTEL":"Defence","MEIL":"Defence","RVNL":"Defence",
    # ── Railways ─────────────────────────────────────────────────────────────
    "RVNL":"Railways","RAILVIKAS":"Railways","IRFC":"Railways","IRCTC":"Railways",
    "IRCON":"Railways","KERNEX":"Railways","RAILTEL":"Railways","TITAGARH":"Railways",
    "TEXRAIL":"Railways","HFCL":"Railways",
    # ── Realty ───────────────────────────────────────────────────────────────
    "DLF":"Realty","GODREJPROP":"Realty","OBEROIRLTY":"Realty","PRESTIGE":"Realty",
    "PHOENIXLTD":"Realty","BRIGADE":"Realty","SOBHA":"Realty","LODHA":"Realty",
    "MAHINDCIE":"Realty","MAHLIFE":"Realty","KOLTEPATIL":"Realty","HEMISPROP":"Realty",
    "SUNTECK":"Realty","ARVSMART":"Realty","INDIGOPNTS":"Realty",
    # ── Consumer Durables ────────────────────────────────────────────────────
    "TITAN":"Consumer Durables","VGUARD":"Consumer Durables","BLUESTARCO":"Consumer Durables",
    "VOLTAS":"Consumer Durables","WHIRLPOOL":"Consumer Durables","CROMPTON":"Consumer Durables",
    "BAJAJEL":"Consumer Durables","ORIENTELEC":"Consumer Durables","KENSTAR":"Consumer Durables",
    "KALONEE":"Consumer Durables","HINDWAREAP":"Consumer Durables","Dixon":"Consumer Durables",
    "AMBER":"Consumer Durables","ACRYSIL":"Consumer Durables","RELAXO":"Consumer Durables",
    "BATAINDIA":"Consumer Durables","KHADIM":"Consumer Durables","PAGEIND":"Consumer Durables",
    # ── Telecom ──────────────────────────────────────────────────────────────
    "BHARTIARTL":"Telecom","IDEA":"Telecom","TATACOMM":"Telecom","HFCL":"Telecom",
    "TEJASNET":"Telecom","STLTECH":"Telecom","VINDHYATEL":"Telecom",
    # ── Media & Entertainment ────────────────────────────────────────────────
    "ZEEL":"Media","SUNTV":"Media","PVRINOX":"Media","NETWORK18":"Media",
    "TV18BRDCST":"Media","TVTODAY":"Media","NAZARA":"Media","SAREGAMA":"Media",
    # ── Chemicals ────────────────────────────────────────────────────────────
    "PIDILITIND":"Chemicals","DEEPAKNITR":"Chemicals","DEEPAKNTR":"Chemicals",
    "GALAXYSURF":"Chemicals","NAVINFLUOR":"Chemicals","SRF":"Chemicals",
    "AARTI":"Chemicals","VINATI":"Chemicals","CLEAN":"Chemicals","TATACHEM":"Chemicals",
    "FINEORG":"Chemicals","BALCHEMI":"Chemicals","CHEMCON":"Chemicals",
    "SUDARSCHEM":"Chemicals","ALKALI":"Chemicals","NOCIL":"Chemicals",
    "CHLORO":"Chemicals","ROSSARI":"Chemicals","VALIANT":"Chemicals",
    "ANUPAM":"Chemicals","MEGHMANI":"Chemicals","KIRI":"Chemicals",
    # ── Retail & E-commerce ──────────────────────────────────────────────────
    "DMART":"Retail","TRENT":"Retail","ABFRL":"Retail","VMART":"Retail",
    "SHOPERSTOP":"Retail","ZOMATO":"Retail","NYKAA":"Retail","FIRSTCRY":"Retail",
    # ── Textile ──────────────────────────────────────────────────────────────
    "PAGEIND":"Textile","ARVIND":"Textile","SIYARAM":"Textile","WELSPUN":"Textile",
    "RTNPOWER":"Textile","TRIDENT":"Textile","VARDHACRLC":"Textile","RAYMOND":"Textile",
    "GOKALDAS":"Textile","KITEX":"Textile","INDO":"Textile","RUPA":"Textile",
    # ── Logistics ────────────────────────────────────────────────────────────
    "DELHIVERY":"Logistics","VRL":"Logistics","MAHINDLOG":"Logistics",
    "BLUEDART":"Logistics","ALLCARGO":"Logistics","GATEWAY":"Logistics",
    "TCIEXP":"Logistics","GATI":"Logistics","AEGIS":"Logistics",
    # ── Agriculture & Fertilisers ────────────────────────────────────────────
    "COROMANDEL":"Agriculture","CHAMBERFL":"Agriculture","RALLIS":"Agriculture",
    "PI":"Agriculture","KAVERI":"Agriculture","JUBLPHARMA":"Agriculture",
    "NFL":"Agriculture","GNFC":"Agriculture","FACT":"Agriculture",
    # ── PSU / Government ─────────────────────────────────────────────────────
    "RECLTD":"PSU","PFC":"PSU","IRFC":"PSU","HUDCO":"PSU",
    "IREDA":"PSU","BPCL":"PSU","IOC":"PSU","ONGC":"PSU","COALINDIA":"PSU",
    "CONCOR":"PSU","NBCC":"PSU","RVNL":"PSU","HAL":"PSU","BEL":"PSU",
}


def download_sector_map() -> pd.DataFrame:
    """Download all sector index files and return a SYMBOL→SECTOR DataFrame."""
    session = requests.Session()
    session.headers.update(_HEADERS)

    rows: list[dict] = []
    for filename, sector in SECTOR_INDICES.items():
        url = BASE_URL + filename
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code == 404:
                log.warning("Not found: %s", filename)
                continue
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            df.columns = df.columns.str.strip()
            sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
            if sym_col is None:
                log.warning("No symbol column in %s  (cols: %s)", filename, list(df.columns))
                continue
            for sym in df[sym_col].str.strip().str.upper().dropna():
                rows.append({"symbol": sym, "sector": sector})
            log.info("%-35s → %d stocks  (%s)", filename, len(df), sector)
            time.sleep(0.3)
        except Exception as exc:
            log.warning("Failed %s: %s", filename, exc)

    if not rows:
        log.warning("NSE download failed — using built-in fallback mapping (%d stocks)", len(FALLBACK_MAPPING))
        rows = [{"symbol": k, "sector": v} for k, v in FALLBACK_MAPPING.items()]

    # If a symbol appears in multiple indices, keep the first (most specific)
    mapping = pd.DataFrame(rows).drop_duplicates(subset="symbol", keep="first")
    log.info("Total unique symbols with sector: %d", len(mapping))
    return mapping


def load_into_duckdb(mapping: pd.DataFrame) -> None:
    """Add sector_map table to DuckDB and rebuild signals with sector info."""
    store = get_store()
    con = store.connect()

    log.info("Loading sector_map into DuckDB (%d rows)…", len(mapping))
    con.execute("CREATE OR REPLACE TABLE sector_map AS SELECT * FROM mapping")

    # Patch the signals table with sector info
    log.info("Adding sector column to signals table…")
    con.execute("""
        CREATE OR REPLACE TABLE signals AS
        SELECT s.*, COALESCE(sm.sector, 'Other') AS sector
        FROM signals s
        LEFT JOIN sector_map sm USING (symbol)
    """)

    count = con.execute("SELECT COUNT(DISTINCT sector) FROM signals").fetchone()[0]
    log.info("signals table now has %d distinct sectors", count)


def main() -> None:
    out_csv = RAW_DATA_DIR / "sector_map.csv"

    log.info("Downloading NSE sector index constituent files…")
    mapping = download_sector_map()

    mapping.to_csv(out_csv, index=False)
    log.info("Saved → %s", out_csv)

    load_into_duckdb(mapping)
    log.info("Done.")


if __name__ == "__main__":
    main()

# universe.py
#
# Loads and validates the country ETF universe from Excel.
# This file is responsible ONLY for:
#   - reading the .xlsx
#   - normalizing column names and values
#   - validating required fields
#   - parsing manual macro columns (if present)
#
# It should NOT compute signals or fetch market data.

from __future__ import annotations

from typing import Optional
import pandas as pd


REQUIRED_COLS = {"Country", "ETF"}

# Optional manual macro columns you may maintain in the Excel
OPTIONAL_COLS = [
    "PolicyRate",          # current policy/short rate level (%, from Trading Economics)
    "PolicyRate_3M_Ago",   # policy rate 3 months ago (%, optional)
    "CPI_YoY",             # inflation YoY (%, optional)
    "GrowthMomentum",      # -1 / 0 / +1 (optional)
    "FX_Regime",           # FreeFloat | Managed | Pegged (optional)
    "CurrentAccount_GDP",  # current account balance (% GDP, optional)
    "RiskFlag",            # 0/1/2 (optional)
]


def _clean_str(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def _to_float(x) -> Optional[float]:
    if pd.isna(x):
        return None
    try:
        # allow strings like "5.25%" or "5,25"
        s = str(x).strip().replace("%", "").replace(",", "")
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def load_country_universe(path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name)

    # ---- FIX: handle multiple sheets safely ----
    if isinstance(df, dict):
        # take the first sheet deterministically
        df = next(iter(df.values()))

    """
    Read the Excel universe file and return a normalized DataFrame.

    Expected minimum columns:
      - Country
      - ETF

    Optional columns (if present) are carried through and parsed into numeric where appropriate.
    """
    df = pd.read_excel(path, sheet_name=sheet_name)

    # Normalize column names (strip whitespace)
    df.columns = [str(c).strip() for c in df.columns]

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"Universe is missing required columns: {sorted(missing)}.\n"
            f"Found columns: {list(df.columns)}"
        )

    # Keep only known columns + any extras (extras are preserved but not relied upon)
    # First, ensure required columns are present
    df = df.copy()

    # Normalize Country / ETF
    df["Country"] = df["Country"].apply(_clean_str)
    df["ETF"] = df["ETF"].apply(_clean_str).str.upper()

    # Drop empty rows
    df = df[(df["Country"] != "") & (df["ETF"] != "")].copy()

    # Parse numeric optional fields if present
    for col in ["PolicyRate", "PolicyRate_3M_Ago", "CPI_YoY", "CurrentAccount_GDP", "RiskFlag"]:
        if col in df.columns:
            df[col] = df[col].apply(_to_float)

    # Parse GrowthMomentum if present (accept numeric or strings)
    if "GrowthMomentum" in df.columns:
        def _gm(x):
            if pd.isna(x):
                return None
            s = str(x).strip()
            if s == "":
                return None
            # allow "accelerating/flat/decelerating"
            low = s.lower()
            if low in ("accelerating", "up", "positive", "+1", "1"):
                return 1.0
            if low in ("decelerating", "down", "negative", "-1"):
                return -1.0
            if low in ("flat", "0", "neutral"):
                return 0.0
            try:
                v = float(s)
                # clamp to [-1, 1]
                return max(-1.0, min(1.0, v))
            except Exception:
                return None

        df["GrowthMomentum"] = df["GrowthMomentum"].apply(_gm)

    # Normalize FX_Regime if present
    if "FX_Regime" in df.columns:
        def _fxr(x):
            s = _clean_str(x).lower()
            if s in ("pegged", "peg"):
                return "Pegged"
            if s in ("managed", "crawl", "band"):
                return "Managed"
            if s in ("freefloat", "free", "float", "floating"):
                return "FreeFloat"
            return _clean_str(x) if _clean_str(x) else None

        df["FX_Regime"] = df["FX_Regime"].apply(_fxr)

    # De-duplicate by Country (keep first)
    df = df.drop_duplicates(subset=["Country"], keep="first").reset_index(drop=True)

    # Final sanity checks
    if df.empty:
        raise ValueError("Universe loaded but contains no valid (Country, ETF) rows.")

    return df

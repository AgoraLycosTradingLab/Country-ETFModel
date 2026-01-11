# run_rank.py
#
# Country ETF Macro Allocator
# ---------------------------
# End-to-end runner:
#   - Loads country ETF universe + manual macro data from Excel
#   - Pulls ETF prices from Yahoo Finance
#   - Pulls FX vs USD from Yahoo Finance
#   - Computes market + macro features
#   - Ranks top K favorable countries
#   - Saves output to data/top10_countries.csv
#
# Usage:
#   python run_rank.py
#
# Requirements:
#   See requirements.txt

from pathlib import Path
import pandas as pd

from config import ModelConfig
from universe import load_country_universe
from model import CountryRanker
from data_providers import (
    YFinancePriceProvider,
    YahooFXProvider,
)

# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

UNIVERSE_XLSX = DATA_DIR / "Country ETF list.xlsx"
OUTPUT_CSV = DATA_DIR / "top10_countries.csv"

START_DATE = "2015-01-01"  # enough history for MA200 + 12M momentum

# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def main():
    # ---- Sanity checks ---------------------------------------------------------------
    if not UNIVERSE_XLSX.exists():
        raise FileNotFoundError(
            f"Universe file not found:\n{UNIVERSE_XLSX}\n"
            "Ensure Country ETF list.xlsx exists in the data/ directory."
        )

    # ---- Load universe (ETF + manual macro) ------------------------------------------
    universe = load_country_universe(str(UNIVERSE_XLSX))

    if universe.empty:
        raise RuntimeError("Universe loaded but is empty.")

    # ---- Providers -------------------------------------------------------------------
    price_provider = YFinancePriceProvider()
    fx_provider = YahooFXProvider(
        print_missing=True,
        print_failed=True
    )

    # ---- Model configuration ---------------------------------------------------------
    cfg = ModelConfig(
        top_k=10,

        # Trend / gates
        require_etf_above_ma200=True,

        # FX handling
        hard_veto_on_fx_breakdown=False,

        # Weights (example – adjust freely)
        weight_equity=0.30,
        weight_fx=0.25,
        weight_real_rate=0.20,
        weight_rate_change=0.15,
        weight_structural=0.10,
    )

    # ---- Ranker ----------------------------------------------------------------------
    ranker = CountryRanker(
        cfg=cfg,
        price_provider=price_provider,
        fx_provider=fx_provider,
    )

    # ---- Run ranking -----------------------------------------------------------------
    ranked = ranker.rank_top_k(
        universe=universe,
        start=START_DATE,
    )

    # ---- Output ----------------------------------------------------------------------
    cols = [
        "Country",
        "ETF",
        "Score",
        "Trend_OK",
        "ETF_Mom_12m",
        "FX_Mom_12m",
        "FX_Mom_3m",
        "PolicyRate",
        "CPI_YoY",
        "RealRate",
        "RateChange_3M",
        "GrowthMomentum",
        "FX_Regime",
    ]
    cols = [c for c in cols if c in ranked.columns]

    print("\n=== TOP FAVORABLE COUNTRIES (MODEL OUTPUT) ===\n")

    if ranked.empty:
        print("No eligible countries. Check gates, FX coverage, or data availability.")
    else:
        print(ranked[cols].to_string(index=False))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(OUTPUT_CSV, index=False)

    print(f"\nSaved output to: {OUTPUT_CSV}")

    # ---- Diagnostics -----------------------------------------------------------------
    print("\nDiagnostics:")
    print(f"  Universe size: {len(universe)}")
    print(f"  Eligible after gates: {len(ranked)}")

    if "FX_Regime" in universe.columns:
        pegged = universe["FX_Regime"].fillna("").str.lower().eq("pegged").sum()
        print(f"  Pegged FX regimes: {pegged}")

    if "PolicyRate" in universe.columns:
        missing_rates = universe["PolicyRate"].isna().sum()
        print(f"  Missing policy rates: {missing_rates}")

    print("\nNotes:")
    print("  - Rankings are relative within the universe.")
    print("  - Market data (ETF + FX) updates daily.")
    print("  - Macro data updates when you update the Excel file.")


# --------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()

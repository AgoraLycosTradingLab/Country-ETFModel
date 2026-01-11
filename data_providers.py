# data_providers.py
#
# Market data providers for the Country ETF Macro Allocator (no-OECD).
#
# Responsibilities:
#   - ETF prices via Yahoo Finance
#   - FX vs USD via Yahoo Finance (standardized: higher = stronger local currency)
#
# This file intentionally avoids macro APIs.
# Macro inputs come from Excel (Trading Economics, manual curation).

from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
import pandas as pd


# --------------------------------------------------------------------------------------
# Base interfaces (lightweight, informal)
# --------------------------------------------------------------------------------------

class PriceProvider:
    def get_adjusted_close(self, tickers: List[str], start: str) -> pd.DataFrame:
        raise NotImplementedError


class FXProvider:
    def get_fx_vs_usd(self, countries: List[str], start: str) -> pd.DataFrame:
        raise NotImplementedError


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def _extract_close_as_series(data: pd.DataFrame, ticker: str) -> Optional[pd.Series]:
    """
    Normalize yfinance output so Close is always returned as a Series.
    Handles Series, 1-col DataFrame, or multi-col DataFrame cases.
    """
    if not isinstance(data, pd.DataFrame) or data.empty:
        return None
    if "Close" not in data.columns:
        return None

    close = data["Close"]

    if isinstance(close, pd.Series):
        return close

    if isinstance(close, pd.DataFrame):
        # Single column
        if close.shape[1] == 1:
            return close.iloc[:, 0]
        # If ticker present
        if ticker in close.columns:
            s = close[ticker]
            if isinstance(s, pd.Series):
                return s
        # Fallback: first column
        return close.iloc[:, 0]

    return None


# --------------------------------------------------------------------------------------
# Yahoo Finance: ETF Prices
# --------------------------------------------------------------------------------------

class YFinancePriceProvider(PriceProvider):
    """
    Fetches daily adjusted-close prices for ETFs using Yahoo Finance.
    """
    def __init__(self):
        import yfinance as yf
        self.yf = yf

    def get_adjusted_close(self, tickers: List[str], start: str) -> pd.DataFrame:
        tickers = [str(t).upper().strip() for t in tickers if isinstance(t, str) and t.strip()]
        tickers = list(dict.fromkeys(tickers))  # de-dup

        if not tickers:
            return pd.DataFrame()

        data = self.yf.download(
            tickers=tickers,
            start=start,
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=True,
        )

        if not isinstance(data, pd.DataFrame) or data.empty:
            return pd.DataFrame()

        try:
            close = data["Close"]
        except Exception:
            return pd.DataFrame()

        if isinstance(close, pd.Series):
            close = close.to_frame()

        close = close.sort_index()
        close.columns = [str(c).upper() for c in close.columns]
        return close


# --------------------------------------------------------------------------------------
# Yahoo Finance: FX vs USD
# --------------------------------------------------------------------------------------

class YahooFXProvider(FXProvider):
    """
    FX provider using Yahoo Finance FX tickers.

    Output is standardized so:
      higher value = stronger local currency vs USD

    Rule:
      - If ticker behaves like USD/LOCAL (e.g., USDJPY), set invert=True → 1/px
      - If ticker behaves like LOCALUSD (e.g., EURUSD), set invert=False
    """

    FX_MAP: Dict[str, Dict[str, Any]] = {
        # Euro bloc (proxy with EUR)
        "Austria": {"ticker": "EUR=X", "invert": False},
        "Belgium": {"ticker": "EUR=X", "invert": False},
        "France": {"ticker": "EUR=X", "invert": False},
        "Germany": {"ticker": "EUR=X", "invert": False},
        "Ireland": {"ticker": "EUR=X", "invert": False},
        "Italy": {"ticker": "EUR=X", "invert": False},
        "Netherlands": {"ticker": "EUR=X", "invert": False},
        "Spain": {"ticker": "EUR=X", "invert": False},

        # Developed
        "Australia": {"ticker": "AUD=X", "invert": False},
        "Canada": {"ticker": "CAD=X", "invert": True},
        "Denmark": {"ticker": "DKK=X", "invert": True},
        "Norway": {"ticker": "NOK=X", "invert": True},
        "Sweden": {"ticker": "SEK=X", "invert": True},
        "Switzerland": {"ticker": "CHF=X", "invert": True},
        "United Kingdom": {"ticker": "GBP=X", "invert": False},
        "Japan": {"ticker": "JPY=X", "invert": True},
        "New Zealand": {"ticker": "NZD=X", "invert": False},

        # Asia
        "China": {"ticker": "CNY=X", "invert": True},
        "Hong Kong": {"ticker": "HKD=X", "invert": True},
        "India": {"ticker": "INR=X", "invert": True},
        "Indonesia": {"ticker": "IDR=X", "invert": True},
        "Malaysia": {"ticker": "MYR=X", "invert": True},
        "Philippines": {"ticker": "PHP=X", "invert": True},
        "Philipines": {"ticker": "PHP=X", "invert": True},  # spelling in Excel
        "Singapore": {"ticker": "SGD=X", "invert": True},
        "South Korea": {"ticker": "KRW=X", "invert": True},
        "Taiwan": {"ticker": "TWD=X", "invert": True},
        "Thailand": {"ticker": "THB=X", "invert": True},

        # LatAm
        "Brazil": {"ticker": "BRL=X", "invert": True},
        "Chile": {"ticker": "CLP=X", "invert": True},
        "Mexico": {"ticker": "MXN=X", "invert": True},
        "Peru": {"ticker": "PEN=X", "invert": True},

        # EMEA / Middle East
        "Poland": {"ticker": "PLN=X", "invert": True},
        "South Africa": {"ticker": "ZAR=X", "invert": True},
        "Turkey": {"ticker": "TRY=X", "invert": True},
        "Israel": {"ticker": "ILS=X", "invert": True},

        # Gulf (often pegged)
        "Saudi Arabia": {"ticker": "SAR=X", "invert": True},
        "United Arab Emirates": {"ticker": "AED=X", "invert": True},
        "Qatar": {"ticker": "QAR=X", "invert": True},
        "Kuwait": {"ticker": "KWD=X", "invert": True},
    }

    def __init__(self, print_missing: bool = True, print_failed: bool = True):
        import yfinance as yf
        self.yf = yf
        self.print_missing = print_missing
        self.print_failed = print_failed

    def _resolve(self, country: str) -> Optional[Dict[str, Any]]:
        spec = self.FX_MAP.get(country)
        if not spec:
            return None
        return {
            "ticker": str(spec["ticker"]),
            "invert": bool(spec.get("invert", True)),
        }

    def get_fx_vs_usd(self, countries: List[str], start: str) -> pd.DataFrame:
        series: Dict[str, pd.Series] = {}
        missing: List[str] = []
        failed: List[Tuple[str, str, str]] = []

        for country in countries:
            spec = self._resolve(country)
            if spec is None:
                missing.append(country)
                continue

            ticker = spec["ticker"]
            invert = spec["invert"]

            try:
                data = self.yf.download(
                    tickers=ticker,
                    start=start,
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
            except Exception as e:
                failed.append((country, ticker, f"exception:{type(e).__name__}"))
                continue

            px = _extract_close_as_series(data, ticker)
            if px is None:
                failed.append((country, ticker, "close_unreadable"))
                continue

            px = px.dropna().astype(float)
            if px.empty:
                failed.append((country, ticker, "empty_close"))
                continue

            fx = (1.0 / px) if invert else px
            fx = fx.dropna()
            if fx.empty:
                failed.append((country, ticker, "empty_fx"))
                continue

            fx.index = pd.to_datetime(fx.index)
            fx.name = country
            series[country] = fx

        if self.print_missing and missing:
            print("\n[FX] Missing FX_MAP entries for:", missing)

        if self.print_failed and failed:
            print("\n[FX] Download failed for (country, ticker, reason):")
            for row in failed[:40]:
                print(" ", row)
            if len(failed) > 40:
                print(f"  ...and {len(failed) - 40} more")

        if not series:
            return pd.DataFrame()

        out = pd.concat(series.values(), axis=1)
        out.columns = list(series.keys())
        out = out.sort_index()
        return out

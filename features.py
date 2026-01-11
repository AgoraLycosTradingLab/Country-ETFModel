# features.py
#
# Stateless feature/utility functions for the Country ETF Macro Allocator.
# Keep this file free of any I/O, providers, or model state so it’s easy to test.

from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd


def pct_change_n_days(s: pd.Series, n_days: int) -> float:
    """
    Percent change over the last n_days (trading days) using the latest available value.
    Returns NaN if insufficient history.
    """
    if s is None or not isinstance(s, pd.Series):
        return float("nan")
    s = s.dropna()
    if len(s) <= n_days:
        return float("nan")
    start = float(s.iloc[-n_days - 1])
    end = float(s.iloc[-1])
    if start == 0.0:
        return float("nan")
    return (end / start) - 1.0


def moving_average(s: pd.Series, window: int) -> Optional[pd.Series]:
    """
    Simple moving average. Returns None if input is invalid.
    """
    if s is None or not isinstance(s, pd.Series):
        return None
    s = s.dropna()
    if s.empty or window <= 1:
        return None
    return s.rolling(window=window, min_periods=window).mean()


def zscore_cross_section(x: pd.Series) -> pd.Series:
    """
    Cross-sectional z-score:
      z = (x - mean) / std
    Ignores NaNs. Returns NaNs where x is NaN.

    If std is ~0 (all values equal), returns 0 for non-NaN entries.
    """
    if x is None or not isinstance(x, pd.Series):
        return pd.Series(dtype=float)

    x = x.astype(float)
    mu = x.mean(skipna=True)
    sigma = x.std(skipna=True)

    if sigma is None or np.isnan(sigma) or sigma < 1e-12:
        # All equal or insufficient variance -> 0 for non-NaN
        out = x.copy()
        out.loc[~out.isna()] = 0.0
        return out

    return (x - mu) / sigma


def safe_clip(x: pd.Series, lo: float, hi: float) -> pd.Series:
    """
    Clip a Series to [lo, hi]. Keeps NaNs as NaN.
    """
    if x is None or not isinstance(x, pd.Series):
        return pd.Series(dtype=float)
    return x.clip(lo, hi)


def winsorize_series(x: pd.Series, p: float = 0.02) -> pd.Series:
    """
    Winsorize a Series at tails p and (1-p). Keeps NaNs.
    """
    if x is None or not isinstance(x, pd.Series):
        return pd.Series(dtype=float)
    if x.dropna().empty:
        return x

    lo = x.quantile(p)
    hi = x.quantile(1 - p)
    return x.clip(lo, hi)


def relative_strength(etf_px: pd.Series, bench_px: pd.Series, n_days: int = 252) -> float:
    """
    Relative strength = (ETF return over n_days) - (Benchmark return over n_days)
    Both inputs should be aligned daily series. Returns NaN if insufficient history.
    """
    if etf_px is None or bench_px is None:
        return float("nan")
    if not isinstance(etf_px, pd.Series) or not isinstance(bench_px, pd.Series):
        return float("nan")

    # Align on dates
    df = pd.concat([etf_px.rename("etf"), bench_px.rename("bench")], axis=1).dropna()
    if len(df) <= n_days:
        return float("nan")

    etf_ret = pct_change_n_days(df["etf"], n_days)
    bench_ret = pct_change_n_days(df["bench"], n_days)

    if np.isnan(etf_ret) or np.isnan(bench_ret):
        return float("nan")

    return etf_ret - bench_ret

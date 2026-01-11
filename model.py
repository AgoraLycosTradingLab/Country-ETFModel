# model.py
#
# Country ETF Macro Allocator (no-OECD design)
#
# Ranks countries based on:
#   - Equity ETF trend confirmation + 12M momentum
#   - FX momentum vs USD (3M + 12M), peg-aware
#   - Manual macro columns from Excel:
#       PolicyRate, PolicyRate_3M_Ago, CPI_YoY, GrowthMomentum, CurrentAccount_GDP, RiskFlag, FX_Regime
#   - Derived macro:
#       RealRate = PolicyRate - CPI_YoY
#       RateChange_3M = PolicyRate - PolicyRate_3M_Ago
#
# Output: ranked DataFrame with Score and feature columns.

from __future__ import annotations

from dataclasses import asdict
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

from config import ModelConfig
from features import (
    pct_change_n_days,
    moving_average,
    zscore_cross_section,
)


class CountryRanker:
    def __init__(self, cfg: ModelConfig, price_provider, fx_provider):
        self.cfg = cfg
        self.px = price_provider
        self.fx = fx_provider
        self.cfg.validate()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_float(self, x) -> float:
        try:
            if x is None or (isinstance(x, float) and np.isnan(x)):
                return np.nan
            return float(x)
        except Exception:
            return np.nan

    def _fx_regime_multiplier(self, fx_regime: Optional[str]) -> float:
        """
        Reduce the impact of FX signals for pegged regimes.
        cfg.fx_peg_penalty = fraction to penalize (e.g., 0.70 => keep 30% of FX)
        """
        if not fx_regime:
            return 1.0
        if str(fx_regime).strip().lower() == "pegged":
            return max(0.0, 1.0 - float(self.cfg.fx_peg_penalty))
        return 1.0

    def _trend_ok(self, etf_px: pd.Series) -> bool:
        ma = moving_average(etf_px, self.cfg.ma_trend_days)
        if ma is None or ma.empty or etf_px is None or etf_px.empty:
            return False
        # latest close above MA
        return bool(etf_px.iloc[-1] > ma.iloc[-1])

    def _clip(self, s: pd.Series) -> pd.Series:
        if not self.cfg.clip_scores:
            return s
        return s.clip(self.cfg.score_clip_min, self.cfg.score_clip_max)

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def rank_top_k(self, universe: pd.DataFrame, start: str) -> pd.DataFrame:
        """
        universe: DataFrame from universe.py (Country, ETF, plus optional manual macro columns)
        start: YYYY-MM-DD for market data start
        """
        df = universe.copy()

        # ---- Fetch market data -------------------------------------------------------
        etfs = df["ETF"].astype(str).str.upper().tolist()
        countries = df["Country"].astype(str).tolist()

        etf_px = self.px.get_adjusted_close(etfs, start=start)  # columns=tickers
        fx_px = self.fx.get_fx_vs_usd(countries, start=start)   # columns=countries

        # ---- Build per-country features ----------------------------------------------
        rows: List[Dict[str, Any]] = []

        for _, row in df.iterrows():
            country = str(row["Country"])
            etf = str(row["ETF"]).upper()

            # ETF series
            s_etf = etf_px[etf].dropna() if (isinstance(etf_px, pd.DataFrame) and etf in etf_px.columns) else pd.Series(dtype=float)
            # FX series
            s_fx = fx_px[country].dropna() if (isinstance(fx_px, pd.DataFrame) and country in fx_px.columns) else pd.Series(dtype=float)

            # Equity features
            etf_mom_12m = pct_change_n_days(s_etf, self.cfg.mom_12m_days)
            trend_ok = self._trend_ok(s_etf) if len(s_etf) >= self.cfg.ma_trend_days else False

            # FX features (can be empty for pegged/unavailable)
            fx_mom_12m = pct_change_n_days(s_fx, self.cfg.mom_12m_days)
            fx_mom_3m = pct_change_n_days(s_fx, self.cfg.mom_3m_days)

            # Manual macro columns
            policy = self._safe_float(row.get("PolicyRate", np.nan))
            policy_3m = self._safe_float(row.get("PolicyRate_3M_Ago", np.nan))
            cpi = self._safe_float(row.get("CPI_YoY", np.nan))

            growth_mom = self._safe_float(row.get("GrowthMomentum", np.nan))
            ca_gdp = self._safe_float(row.get("CurrentAccount_GDP", np.nan))
            riskflag = self._safe_float(row.get("RiskFlag", np.nan))
            fx_regime = row.get("FX_Regime", None)

            # Derived macro
            real_rate = policy - cpi if (not np.isnan(policy) and not np.isnan(cpi)) else np.nan
            rate_change_3m = policy - policy_3m if (not np.isnan(policy) and not np.isnan(policy_3m)) else np.nan

            rows.append({
                "Country": country,
                "ETF": etf,
                "Trend_OK": bool(trend_ok),
                "ETF_Mom_12m": etf_mom_12m,
                "FX_Mom_12m": fx_mom_12m,
                "FX_Mom_3m": fx_mom_3m,
                "PolicyRate": policy,
                "PolicyRate_3M_Ago": policy_3m,
                "CPI_YoY": cpi,
                "RealRate": real_rate,
                "RateChange_3M": rate_change_3m,
                "GrowthMomentum": growth_mom,
                "CurrentAccount_GDP": ca_gdp,
                "RiskFlag": riskflag,
                "FX_Regime": fx_regime,
            })

        feat = pd.DataFrame(rows)

        # ---- Gates / eligibility ------------------------------------------------------
        eligible = feat.copy()

        if self.cfg.require_etf_above_ma200:
            eligible = eligible[eligible["Trend_OK"] == True].copy()

        if self.cfg.drop_if_missing_policy_rate and "PolicyRate" in eligible.columns:
            eligible = eligible[~eligible["PolicyRate"].isna()].copy()

        if self.cfg.drop_if_missing_cpi and "CPI_YoY" in eligible.columns:
            eligible = eligible[~eligible["CPI_YoY"].isna()].copy()

        if eligible.empty:
            return eligible

        # ---- Cross-sectional standardization -----------------------------------------
        # Equity z-score
        z_equity = zscore_cross_section(eligible["ETF_Mom_12m"])
        # FX combo: average of 12m and 3m momentums
        fx_combo = (eligible["FX_Mom_12m"].astype(float) + eligible["FX_Mom_3m"].astype(float)) / 2.0
        z_fx = zscore_cross_section(fx_combo)

        # Macro z-scores:
        # RealRate: higher is better
        z_real = zscore_cross_section(eligible["RealRate"])
        # RateChange: easing (negative) can be good for growth, tightening (positive) can be good for FX.
        # We treat this as *directional* and let the z-score decide cross-sectionally.
        z_ratechg = zscore_cross_section(eligible["RateChange_3M"])

        # Structural: combine GrowthMomentum + CurrentAccount - RiskFlag penalty
        structural_raw = pd.Series(0.0, index=eligible.index, dtype=float)

        if "GrowthMomentum" in eligible.columns:
            structural_raw = structural_raw.add(eligible["GrowthMomentum"].fillna(0.0))

        if "CurrentAccount_GDP" in eligible.columns:
            # scale down CA to avoid dominating (CA is in % GDP)
            structural_raw = structural_raw.add(0.2 * eligible["CurrentAccount_GDP"].fillna(0.0))

        if "RiskFlag" in eligible.columns:
            # higher riskflag => penalty
            structural_raw = structural_raw.sub(0.75 * eligible["RiskFlag"].fillna(0.0))

        z_struct = zscore_cross_section(structural_raw)

        # Missing handling (important to avoid NaN score)
        if self.cfg.fill_missing_with_zero:
            z_equity = z_equity.fillna(0.0)
            z_fx = z_fx.fillna(0.0)
            z_real = z_real.fillna(0.0)
            z_ratechg = z_ratechg.fillna(0.0)
            z_struct = z_struct.fillna(0.0)

        # Clip extreme z-scores
        z_equity = self._clip(z_equity)
        z_fx = self._clip(z_fx)
        z_real = self._clip(z_real)
        z_ratechg = self._clip(z_ratechg)
        z_struct = self._clip(z_struct)

        # ---- FX regime adjustment -----------------------------------------------------
        fx_mult = eligible["FX_Regime"].apply(self._fx_regime_multiplier).astype(float)
        z_fx_adj = z_fx * fx_mult

        # ---- Optional veto: FX breakdown ---------------------------------------------
        if self.cfg.hard_veto_on_fx_breakdown:
            # If FX 12m < 0, exclude
            eligible = eligible[eligible["FX_Mom_12m"].fillna(0.0) >= 0.0].copy()
            # align z-scores
            z_equity = z_equity.loc[eligible.index]
            z_fx_adj = z_fx_adj.loc[eligible.index]
            z_real = z_real.loc[eligible.index]
            z_ratechg = z_ratechg.loc[eligible.index]
            z_struct = z_struct.loc[eligible.index]

        # ---- Score -------------------------------------------------------------------
        score = (
            self.cfg.weight_equity * z_equity
            + self.cfg.weight_fx * z_fx_adj
            + self.cfg.weight_real_rate * z_real
            + self.cfg.weight_rate_change * z_ratechg
            + self.cfg.weight_structural * z_struct
        )

        if self.cfg.clip_scores:
            score = score.clip(self.cfg.score_clip_min, self.cfg.score_clip_max)

        eligible["Score"] = score

        # Sort and return top K
        eligible = eligible.sort_values("Score", ascending=False).reset_index(drop=True)
        topk = eligible.head(self.cfg.top_k).copy()

        if self.cfg.verbose:
            print("\n[DEBUG] Config:", asdict(self.cfg))
            print("[DEBUG] Eligible count:", len(eligible))

        return topk

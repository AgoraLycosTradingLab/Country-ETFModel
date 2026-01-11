# config.py
#
# Central configuration for the Country ETF Macro Allocator
#
# This file defines:
#   - Scoring weights
#   - Lookback windows
#   - Trend / regime gates
#   - Missing-data behavior
#
# Adjust values here to change model behavior globally.

from dataclasses import dataclass


@dataclass
class ModelConfig:
    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    top_k: int = 10

    # ------------------------------------------------------------------
    # Lookback windows (trading days)
    # ------------------------------------------------------------------
    mom_12m_days: int = 252
    mom_3m_days: int = 63
    ma_trend_days: int = 200

    # ------------------------------------------------------------------
    # Trend / eligibility gates
    # ------------------------------------------------------------------
    require_etf_above_ma200: bool = True
    hard_veto_on_fx_breakdown: bool = False  # if True, negative FX momentum excludes country

    # ------------------------------------------------------------------
    # Scoring weights (must sum to 1.0)
    # ------------------------------------------------------------------
    weight_equity: float = 0.30        # ETF momentum + trend
    weight_fx: float = 0.25            # FX momentum vs USD
    weight_real_rate: float = 0.20     # PolicyRate - CPI_YoY
    weight_rate_change: float = 0.15   # PolicyRate - PolicyRate_3M_Ago
    weight_structural: float = 0.10    # GrowthMomentum / CurrentAccount / risk flags

    # ------------------------------------------------------------------
    # FX regime handling
    # ------------------------------------------------------------------
    fx_peg_penalty: float = 0.70
    # FX contribution multiplier when FX_Regime == "Pegged"
    # Example: 0.70 → FX signal contributes only 30% of normal weight

    # ------------------------------------------------------------------
    # Macro thresholds (heuristics, adjust as needed)
    # ------------------------------------------------------------------
    real_rate_bad_threshold: float = -2.0     # deeply negative real rates
    real_rate_good_threshold: float = 1.0     # attractive real rates

    rate_change_significant: float = 0.25     # 25 bps over 3M considered meaningful

    # ------------------------------------------------------------------
    # Missing-data behavior
    # ------------------------------------------------------------------
    fill_missing_with_zero: bool = True
    drop_if_missing_policy_rate: bool = False
    drop_if_missing_cpi: bool = False

    # ------------------------------------------------------------------
    # Safety / normalization
    # ------------------------------------------------------------------
    clip_scores: bool = True
    score_clip_min: float = -3.0
    score_clip_max: float = 3.0

    # ------------------------------------------------------------------
    # Debugging
    # ------------------------------------------------------------------
    verbose: bool = False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self) -> None:
        total_weight = (
            self.weight_equity
            + self.weight_fx
            + self.weight_real_rate
            + self.weight_rate_change
            + self.weight_structural
        )

        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(
                f"Scoring weights must sum to 1.0, got {total_weight:.4f}"
            )

        if self.top_k <= 0:
            raise ValueError("top_k must be positive.")

        if self.mom_12m_days <= self.mom_3m_days:
            raise ValueError("mom_12m_days must be > mom_3m_days.")


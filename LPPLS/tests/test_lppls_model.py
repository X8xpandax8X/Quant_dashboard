from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lppls.config import ScaleConfig
from lppls.models.lppls import LPPLSModel, _Candidate


def _small_model(window: int = 16) -> LPPLSModel:
    scale = ScaleConfig("test", window, "Test horizon", "#ffffff", "solid")
    return LPPLSModel(
        scales=(scale,),
        step_divisor=2,
        confirmation_lookback=2,
        m_grid=(0.5,),
        omega_grid=(8.0,),
        tc_grid_size=2,
    )


def test_endpoint_schedule_always_includes_latest_observation() -> None:
    assert LPPLSModel._endpoint_positions(45, 32, 8) == [32, 40, 45]
    assert LPPLSModel._endpoint_positions(31, 32, 8) == []


def test_nonintegral_scheduling_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        LPPLSModel(step_divisor=0.5)
    with pytest.raises(ValueError, match="positive integer"):
        LPPLSModel(confirmation_lookback=1.5)


def test_oscillation_count_filter_only_applies_above_amplitude_precondition() -> None:
    model = _small_model(window=32)
    candidate = _Candidate(
        tc=47.0,
        A=5.0,
        B=-0.05,
        m=0.5,
        C1=0.0005,
        C2=0.0,
        omega=8.0,
        mse=0.0,
        fitted_log_prices=np.zeros(32),
        design_condition=1.0,
    )

    fit = model._qualify_candidate(
        candidate,
        actual_log_prices=np.zeros(32),
        start_position=0,
        end_position=31,
    )

    assert fit.relative_oscillation_amplitude < 0.05
    assert fit.oscillation_count < 2.5
    assert fit.oscillation_filter_applied is False
    assert fit.passes_oscillation_filter is True
    assert fit.qualified is True


def test_latest_fit_curve_is_aligned_to_the_actual_final_window() -> None:
    dates = pd.date_range("2020-01-05", periods=45, freq="W")
    trend = np.exp(np.linspace(np.log(20), np.log(80), len(dates)))
    prices = pd.Series(trend, index=dates, name="close")

    output = _small_model().analyze(prices)

    row = output.parameter_rows[0]
    diagnostics = output.diagnostics["scales"]["test"]
    assert diagnostics["final_endpoint_included"] is True
    assert row["end_position"] == len(prices) - 1
    assert pd.Timestamp(row["fit_end"]).date() == dates[-1].date()
    assert output.fit_curves[0].values.index[-1] == dates[-1]
    assert output.score_frame.index.equals(dates)
    assert np.isfinite(output.score_frame["composite"].iloc[-1])


def test_insufficient_history_is_reported_without_fake_scores() -> None:
    dates = pd.date_range("2024-01-07", periods=12, freq="W")
    prices = pd.Series(np.linspace(10, 12, len(dates)), index=dates)

    output = _small_model(window=16).analyze(prices)

    assert output.parameter_rows[0]["status"] == "insufficient_history"
    assert output.score_frame["composite"].isna().all()
    assert output.fit_curves == []

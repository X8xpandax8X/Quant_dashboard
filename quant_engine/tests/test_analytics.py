import json
import math

import numpy as np
import pandas as pd
import pytest

from quant_engine.analytics import capm, comparison, distribution, portfolio_analysis, sharpe_ratio, volume_profile
from quant_engine.models import ModelRegistry


def history(returns, initial=100):
    close = initial * np.r_[1, np.cumprod(1 + np.asarray(returns, dtype=float))]
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close,
                         "volume": np.full(len(close), 100.0)},
                        index=pd.date_range("2025-01-01", periods=len(close), freq="B", tz="UTC"))


@pytest.fixture
def market():
    # 60 returns: mean .005, sample variance .0135/59.
    return history(np.tile([-.01, .02], 30))


def test_distribution_known_sample():
    result = distribution(history([-.1, 0, .1]))
    assert result["daily_mean"] == pytest.approx(0, abs=1e-15)
    assert result["daily_volatility"] == pytest.approx(.1)
    assert result["annual_volatility"] == pytest.approx(.1 * math.sqrt(252))
    assert result["win_rate"] == pytest.approx(1 / 3)
    assert result["sample_count"] == 3
    assert sum(b["count"] for b in result["histogram"]) == 3
    assert result["returns"][0]["time"].endswith("Z")


def test_capm_exact_linear_relation(market):
    asset = history(np.tile([-.017, .043], 30))  # 2 * market + .003
    result = capm(asset, market, .04)
    assert result["beta"] == pytest.approx(2)
    assert result["market_return"] == pytest.approx(1.26)
    assert result["actual_return"] == pytest.approx(3.276)
    assert result["expected_return"] == pytest.approx(2.48)
    assert result["alpha"] == pytest.approx(.796)
    assert result["scenario_price"] == pytest.approx(asset.close.iloc[-1] * 3.48)
    assert result["sample_count"] == 60


def test_sharpe_daily_excess_and_last_126(market):
    expected = (.005 - ((1.04 ** (1 / 252)) - 1)) / math.sqrt(.0135 / 59) * math.sqrt(252)
    assert sharpe_ratio(market, .04) == pytest.approx(expected)
    long = history(np.r_[np.full(40, .2), np.tile([-.01, .02], 63)])
    six_month_expected = .005 / math.sqrt(126 * .015**2 / 125) * math.sqrt(252)
    assert sharpe_ratio(long, 0) == pytest.approx(six_month_expected)
    assert sharpe_ratio(market.iloc[:-1], .04) is None
    assert sharpe_ratio(market, None) is None
    assert sharpe_ratio(history(np.zeros(100)), 0) is None


def test_thin_capm_retains_mean_and_price(market):
    result = capm(market.iloc[:10], market, .04)
    assert result["sample_count"] == 9
    assert result["beta"] is None
    assert result["expected_return"] is None
    assert result["actual_return"] is not None
    assert result["current_price"] == market.close.iloc[9]
    assert any("60" in note for note in result["notes"])


def test_no_risk_free_preserves_beta(market):
    result = capm(market, market, None)
    assert result["beta"] == pytest.approx(1)
    assert result["expected_return"] is None
    assert result["alpha"] is None
    assert result["scenario_price"] is None


def test_zero_variance_market(market):
    flat = history(np.zeros(60))
    assert capm(market, flat, 0)["beta"] is None
    result = comparison({"A": market, "FLAT": flat})
    assert all(c["value"] is None for c in result["correlations"] if "FLAT" in (c["x"], c["y"]))
    assert next(c for c in result["correlations"] if c["x"] == c["y"] == "A")["value"] == 1


def test_no_nonpositive_scenario():
    down = history(np.tile([-.01, -.02], 30))
    result = capm(down, down, 0)
    assert result["expected_return"] < -1
    assert result["scenario_price"] is None


def test_missing_timestamp_cannot_bridge_returns(market):
    missing = market.drop(market.index[20])
    result = capm(missing, market, 0)
    assert result["sample_count"] == 58  # Missing bar removes that return AND next day's.
    assert result["beta"] is None
    compare = comparison({"FULL": market, "MISSING": missing})
    pair = next(c for c in compare["correlations"] if c["x"] == "FULL" and c["y"] == "MISSING")
    assert pair["sample_count"] == 58
    points = compare["series"][1]["points"]
    assert points[20]["value"] is None
    explicit = market.copy()
    explicit.loc[explicit.index[20], "close"] = np.nan
    assert distribution(explicit)["sample_count"] == 58


def test_shared_baseline_and_pairwise_overlap(market):
    later = market.iloc[4:]
    result = comparison({"FULL": market, "LATER": later})
    a, b = result["series"]
    assert a["points"][0] == b["points"][0]
    assert a["points"][0]["value"] == 0
    assert a["points"][-1]["value"] == pytest.approx(market.close.iloc[-1] / market.close.iloc[4] - 1)
    assert result["correlations"][0]["sample_count"] == 60
    assert result["correlations"][1]["sample_count"] == 56


def test_portfolio_covariance_beta_sharpe_identities(market):
    second = history(np.tile([.02, -.01], 30))
    result = portfolio_analysis({"A": market, "B": second}, {"A": 7500, "B": 2500}, market, 0)
    metrics = result["metrics"]
    # Daily portfolio returns alternate -.0025/.0125: mean .005, half market std.
    assert metrics["expected_return"] == pytest.approx(1.26)
    assert metrics["volatility"] == pytest.approx(math.sqrt(.0135 / 59 * 252) / 2)
    assert metrics["beta"] == pytest.approx(.5)
    assert metrics["sharpe"] == pytest.approx(1.26 / metrics["volatility"])
    assert metrics["sample_count"] == 60
    assert result["performance"][-1]["portfolio"] == pytest.approx((.9975 * 1.0125)**30 - 1)
    assert result["performance"][-1]["benchmark"] == pytest.approx((.99 * 1.02)**30 - 1)


def test_zero_risk_portfolio(market):
    opposite = history(np.tile([.02, -.01], 30))
    result = portfolio_analysis({"A": market, "B": opposite}, {"A": 5000, "B": 5000}, market, .04)
    assert result["metrics"]["volatility"] == pytest.approx(0, abs=1e-8)
    assert result["metrics"]["beta"] == pytest.approx(0, abs=1e-12)
    assert result["metrics"]["sharpe"] is None


def test_portfolio_uses_same_complete_matrix(market):
    missing = market.drop(market.index[20])
    result = portfolio_analysis({"A": market, "B": missing}, {"A": 5000, "B": 5000}, market, 0)
    assert result["metrics"]["sample_count"] == 58
    assert result["metrics"]["volatility"] is None
    assert result["metrics"]["beta"] is None
    assert result["metrics"]["sharpe"] is None
    assert result["metrics"]["expected_return"] is not None
    assert len(result["performance"]) == 58
    excluded = {market.index[20].isoformat().replace("+00:00", "Z"), market.index[21].isoformat().replace("+00:00", "Z")}
    assert not excluded.intersection(p["time"] for p in result["performance"])


@pytest.mark.parametrize("weights", [{}, {"A": 9999}, {"A": -1, "B": 10001}, {"A": 10000.0}, {"A": True}, {"A": 10000, "B": 0}])
def test_invalid_weights(weights, market):
    with pytest.raises(ValueError):
        portfolio_analysis({"A": market, "B": market}, weights, market, 0)


def test_missing_holding_rejected(market):
    with pytest.raises(ValueError):
        portfolio_analysis({}, {"A": 10000}, market, 0)


def test_volume_conservation_tie_and_contiguous_expansion():
    frame = history([0, 0, 0, 0])
    frame[["high", "low", "close"]] = np.array([10, 11, 12, 13, 14])[:, None] * np.ones((1, 3))
    frame["volume"] = [30, 10, 30, 10, 20]
    result = volume_profile(frame, bins=5)
    assert sum(b["volume"] for b in result["bins"]) == 100
    assert result["poc"] == pytest.approx(10.4)  # first of tied volume maxima
    assert result["val"] == 10
    assert result["vah"] == pytest.approx(12.4)
    assert result["coverage"] == pytest.approx(.7)


def test_volume_neighbor_tie_prefers_lower():
    frame = history([0, 0, 0, 0])
    frame[["high", "low", "close"]] = np.array([10, 11, 12, 13, 14])[:, None] * np.ones((1, 3))
    frame["volume"] = [5, 20, 50, 20, 5]
    result = volume_profile(frame, bins=5)
    assert result["val"] == pytest.approx(10.8)
    assert result["vah"] == pytest.approx(12.4)
    assert result["coverage"] == pytest.approx(.7)


def test_flat_and_missing_volume():
    frame = history([0, 0, 0])
    frame["volume"] = [None, -1, 20, 10]
    result = volume_profile(frame)
    assert result["poc"] == result["val"] == result["vah"] == 100
    assert result["total_volume"] == 30
    assert result["coverage"] == 1
    frame["volume"] = np.nan
    result = volume_profile(frame)
    assert result["total_volume"] is None
    assert result["poc"] is None
    frame["volume"] = 0
    assert volume_profile(frame)["total_volume"] == 0
    assert volume_profile(frame)["poc"] is None


def test_timezone_and_input_immutability(market):
    local = market.copy()
    local.index = local.index.tz_convert("Asia/Bangkok")
    original = local.copy(deep=True)
    assert distribution(local) == distribution(market)
    assert capm(local, market, 0)["beta"] == pytest.approx(1)
    pd.testing.assert_frame_equal(local, original)
    duplicate = pd.concat([market, market.iloc[:1]])
    with pytest.raises(ValueError):
        distribution(duplicate)


def test_nonfinite_inputs_produce_strict_json(market):
    frame = market.copy()
    frame.loc[frame.index[3], "close"] = np.inf
    frame.loc[frame.index[6], "close"] = -np.inf
    frame.loc[frame.index[9], "close"] = 0
    frame.loc[frame.index[11], "volume"] = np.inf
    outputs = [distribution(frame), volume_profile(frame), comparison({"A": frame, "B": market}),
               capm(frame, market, np.inf), portfolio_analysis({"A": frame}, {"A": 10000}, market, np.nan)]
    for output in outputs:
        json.dumps(output, allow_nan=False)
    empty = market.iloc[:0]
    for output in [distribution(empty), volume_profile(empty), comparison({"A": empty}), capm(empty, empty, None),
                   portfolio_analysis({"A": empty}, {"A": 10000}, empty, None)]:
        json.dumps(output, allow_nan=False)


def test_registry_is_opt_in():
    registry = ModelRegistry()
    assert registry.names() == ()
    class Stub:
        name = "future-model"
        def analyze(self, prices):
            return {"status": "unavailable"}
    model = Stub()
    registry.register(model)
    assert registry.get(model.name) is model
    with pytest.raises(ValueError):
        registry.register(model)

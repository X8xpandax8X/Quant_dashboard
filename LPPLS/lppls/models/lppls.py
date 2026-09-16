"""Deterministic multi-horizon LPPLS bubble analysis.

The implementation uses variable projection: nonlinear parameters are searched
on a deterministic grid while the linear LPPLS coefficients are solved with
least squares. Scores emitted by this module are fixed-window temporal
persistence ratios: they describe how consistently recent scheduled fits pass
the configured quality filters. They are not the ensemble LPPLS Confidence
Indicator and are not probabilities of a bubble or crash.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import pi
from typing import Any

import numpy as np
import pandas as pd

from ..config import SCALES, ScaleConfig
from ..types import FitCurve, ModelOutput
from .base import BubbleModel


_MIN_FIT_OBSERVATIONS = 8
_MAX_DESIGN_CONDITION = 1.0e14


@dataclass(frozen=True, slots=True)
class LPPLSFilterConfig:
    """Thresholds used to qualify a fitted LPPLS candidate.

    The B filter is deliberately applied only after the lowest-MSE candidate
    has been selected.  The grid therefore cannot discard a good numerical fit
    merely because its B coefficient does not describe a positive bubble.
    """

    m_min: float = 0.0
    m_max: float = 1.0
    omega_min: float = 4.0
    omega_max: float = 25.0
    min_damping: float = 0.50
    min_oscillations: float = 2.50
    min_relative_oscillation_amplitude: float = 0.05
    max_relative_error: float = 0.20

    def __post_init__(self) -> None:
        values = (
            self.m_min,
            self.m_max,
            self.omega_min,
            self.omega_max,
            self.min_damping,
            self.min_oscillations,
            self.min_relative_oscillation_amplitude,
            self.max_relative_error,
        )
        if not all(np.isfinite(value) for value in values):
            raise ValueError("LPPLS filter thresholds must be finite")
        if self.m_min >= self.m_max:
            raise ValueError("m_min must be smaller than m_max")
        if self.omega_min >= self.omega_max:
            raise ValueError("omega_min must be smaller than omega_max")
        if (
            self.min_damping < 0
            or self.min_oscillations < 0
            or self.min_relative_oscillation_amplitude < 0
        ):
            raise ValueError("LPPLS ratio/count thresholds cannot be negative")
        if self.max_relative_error <= 0:
            raise ValueError("max_relative_error must be positive")

    def as_dict(self) -> dict[str, Any]:
        """Return machine- and dashboard-readable qualification rules."""

        return {
            "B": {"operator": "<", "value": 0.0, "description": "B < 0"},
            "m": {
                "operator": "between_exclusive",
                "minimum": self.m_min,
                "maximum": self.m_max,
            },
            "omega": {
                "operator": "between_inclusive",
                "minimum": self.omega_min,
                "maximum": self.omega_max,
            },
            "damping": {"operator": ">=", "value": self.min_damping},
            "oscillation_count": {
                "operator": ">=",
                "value": self.min_oscillations,
                "precondition": (
                    "hypot(C1, C2) / abs(B) >= "
                    f"{self.min_relative_oscillation_amplitude}"
                ),
            },
            "relative_oscillation_amplitude": {
                "formula": "hypot(C1, C2) / abs(B)",
                "role": "precondition_for_oscillation_count_filter",
                "value": self.min_relative_oscillation_amplitude,
            },
            "max_relative_error": {
                "operator": "<=",
                "value": self.max_relative_error,
            },
        }


@dataclass(frozen=True, slots=True)
class LPPLSFit:
    """One fitted window with inclusive positions in the cleaned price series."""

    start_position: int
    end_position: int
    tc_window_position: float
    tc_absolute_position: float
    A: float
    B: float
    m: float
    C1: float
    C2: float
    omega: float
    mse: float
    max_relative_error: float
    damping: float
    oscillation_count: float
    relative_oscillation_amplitude: float
    design_condition: float
    passes_b_filter: bool
    passes_m_filter: bool
    passes_omega_filter: bool
    passes_damping_filter: bool
    passes_oscillation_filter: bool
    oscillation_filter_applied: bool
    passes_max_relative_error_filter: bool
    qualified: bool

    @property
    def weeks_to_tc(self) -> float:
        """Critical time in observation-weeks after this fit's endpoint."""

        return self.tc_absolute_position - self.end_position


@dataclass(frozen=True, slots=True)
class _Candidate:
    """Lowest-MSE variable-projection candidate before qualification."""

    tc: float
    A: float
    B: float
    m: float
    C1: float
    C2: float
    omega: float
    mse: float
    fitted_log_prices: np.ndarray
    design_condition: float


class LPPLSModel(BubbleModel):
    """Run deterministic LPPLS fits over configured rolling horizons.

    Parameters
    ----------
    scales:
        Rolling horizons.  The defaults are the application's 32-, 104-, and
        208-week scales.  All of them analyze the complete supplied history.
    step_divisor:
        A scale with window ``w`` is refitted every ``max(1, w //
        step_divisor)`` observations.  The final observation is always added as
        an endpoint even when the regular step does not land on it.
    confirmation_lookback:
        Number of scheduled fits in the trailing temporal-persistence ratio.
    filters:
        Post-selection quality thresholds.  No B filter is used during the
        MSE search itself.
    m_grid, omega_grid:
        Optional deterministic nonlinear grids.  Defaults intentionally extend
        beyond the qualification ranges so m and omega checks are meaningful.
    tc_grid_size:
        Number of critical-time candidates between one observation and
        ``max_tc_fraction`` of a window beyond the fit endpoint.
    max_tc_fraction:
        Maximum candidate critical-time horizon as a fraction of the fitting
        window. The estimate remains a coarse grid candidate, not a calibrated
        crash-time forecast.
    """

    key = "lppls"
    name = "LPPLS"

    def __init__(
        self,
        scales: Sequence[ScaleConfig] = SCALES,
        *,
        step_divisor: int = 4,
        confirmation_lookback: int = 8,
        filters: LPPLSFilterConfig | None = None,
        m_grid: Sequence[float] | None = None,
        omega_grid: Sequence[float] | None = None,
        tc_grid_size: int = 8,
        max_tc_fraction: float = 0.20,
    ) -> None:
        self.scales = tuple(scales)
        if not self.scales:
            raise ValueError("LPPLSModel requires at least one scale")
        scale_keys = [scale.key for scale in self.scales]
        if len(scale_keys) != len(set(scale_keys)):
            raise ValueError("LPPLS scale keys must be unique")
        if any(scale.weeks < _MIN_FIT_OBSERVATIONS for scale in self.scales):
            raise ValueError(
                f"Every LPPLS scale needs at least {_MIN_FIT_OBSERVATIONS} observations"
            )
        if (
            isinstance(step_divisor, bool)
            or not isinstance(step_divisor, (int, np.integer))
            or step_divisor <= 0
        ):
            raise ValueError("step_divisor must be a positive integer")
        if (
            isinstance(confirmation_lookback, bool)
            or not isinstance(confirmation_lookback, (int, np.integer))
            or confirmation_lookback <= 0
        ):
            raise ValueError("confirmation_lookback must be a positive integer")
        if (
            isinstance(tc_grid_size, bool)
            or not isinstance(tc_grid_size, (int, np.integer))
            or tc_grid_size < 2
        ):
            raise ValueError("tc_grid_size must be an integer of at least 2")
        if not np.isfinite(max_tc_fraction) or not 0 < max_tc_fraction <= 1:
            raise ValueError("max_tc_fraction must be in (0, 1]")

        self.step_divisor = int(step_divisor)
        self.confirmation_lookback = int(confirmation_lookback)
        self.filters = filters or LPPLSFilterConfig()
        self.m_grid = self._validated_grid(
            m_grid if m_grid is not None else np.linspace(0.05, 1.05, 11),
            name="m_grid",
        )
        self.omega_grid = self._validated_grid(
            omega_grid if omega_grid is not None else np.arange(3.0, 28.0, 2.0),
            name="omega_grid",
        )
        if any(value <= 0 for value in self.m_grid):
            raise ValueError("m_grid values must be positive")
        if any(value <= 0 for value in self.omega_grid):
            raise ValueError("omega_grid values must be positive")
        self.tc_grid_size = int(tc_grid_size)
        self.max_tc_fraction = float(max_tc_fraction)

    @staticmethod
    def _validated_grid(values: Sequence[float], *, name: str) -> tuple[float, ...]:
        grid = tuple(float(value) for value in values)
        if not grid:
            raise ValueError(f"{name} cannot be empty")
        if not all(np.isfinite(value) for value in grid):
            raise ValueError(f"{name} values must be finite")
        return grid

    def analyze(self, prices: pd.Series) -> ModelOutput:
        """Analyze a complete positive weekly price series.

        Invalid/non-positive observations are removed, duplicate dates retain
        their last value, and the remaining observations are sorted.  Score
        columns are carried forward between scheduled refits. Forecast columns
        contain point estimates only for qualified scheduled fits; rejected
        candidates are kept in diagnostics but are not presented as forecasts.
        """

        clean_prices, preparation = self._prepare_prices(prices)
        observation_count = len(clean_prices)
        log_prices = np.log(clean_prices.to_numpy(dtype=float))

        score_frame = pd.DataFrame(index=clean_prices.index)
        forecast_frame = pd.DataFrame(index=clean_prices.index)
        fit_curves: list[FitCurve] = []
        parameter_rows: list[dict[str, Any]] = []
        scale_diagnostics: dict[str, Any] = {}

        for scale in self.scales:
            scale_result = self._analyze_scale(log_prices, clean_prices, scale)
            score_frame[scale.key] = scale_result["score"]
            forecast_frame[scale.key] = scale_result["forecast"]
            scale_diagnostics[scale.key] = scale_result["diagnostics"]

            latest_fit: LPPLSFit | None = scale_result["latest_fit"]
            if latest_fit is None:
                parameter_rows.append(
                    {
                        "model": self.name,
                        "scale": scale.label,
                        "scale_key": scale.key,
                        "horizon_weeks": scale.weeks,
                        "status": (
                            "insufficient_history"
                            if observation_count < scale.weeks
                            else "no_numerically_stable_fit"
                        ),
                        "observations": observation_count,
                    }
                )
                continue

            fit_values = (
                self._fit_curve(latest_fit, clean_prices)
                if latest_fit.qualified
                else None
            )
            if fit_values is not None:
                fit_curves.append(
                    FitCurve(
                        key=scale.key,
                        label=f"LPPLS {scale.label}",
                        color=scale.color,
                        dash=scale.dash,
                        values=fit_values,
                    )
                )

            latest_ratio = float(score_frame.at[clean_prices.index[-1], scale.key])
            parameter_rows.append(
                self._parameter_row(
                    latest_fit,
                    clean_prices,
                    scale,
                    latest_ratio=latest_ratio,
                )
            )

        scale_columns = [scale.key for scale in self.scales]
        score_frame["composite"] = score_frame[scale_columns].mean(axis=1, skipna=True)
        available_scales = score_frame[scale_columns].notna().sum(axis=1)
        score_frame.loc[available_scales < len(scale_columns), "composite"] = np.nan
        score_frame = score_frame.astype(float)
        forecast_frame = forecast_frame.astype(float)

        diagnostics: dict[str, Any] = {
            "score_kind": "fixed_window_temporal_persistence_ratio",
            "score_description": (
                "Trailing share of scheduled fixed-window LPPLS fits that pass "
                "every qualification filter. This temporal-persistence heuristic "
                "is not the cross-window LPPLS Confidence Indicator and is not a "
                "probability of a bubble or crash."
            ),
            "score_alignment": (
                "Each scale is carried forward between scheduled refits; the "
                "composite is the equal-weight mean of available scale ratios."
            ),
            "forecast_description": (
                "Weeks to tc for qualified fits only. Values are coarse-grid "
                "diagnostic estimates, not calibrated crash-time forecasts."
            ),
            "mse_domain": "log_price",
            "step_divisor": self.step_divisor,
            "confirmation_lookback": self.confirmation_lookback,
            "tc_grid_size": self.tc_grid_size,
            "max_tc_fraction": self.max_tc_fraction,
            "optimization": "deterministic_coarse_grid_variable_projection",
            "m_grid": list(self.m_grid),
            "omega_grid": list(self.omega_grid),
            "maximum_design_condition": _MAX_DESIGN_CONDITION,
            "qualification_filters": self.filters.as_dict(),
            "input_observations": preparation["input_observations"],
            "used_observations": observation_count,
            "dropped_observations": preparation["dropped_observations"],
            "scales": scale_diagnostics,
        }

        return ModelOutput(
            model_key=self.key,
            model_name=self.name,
            score_frame=score_frame,
            fit_curves=fit_curves,
            forecast_frame=forecast_frame,
            parameter_rows=parameter_rows,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _prepare_prices(prices: pd.Series) -> tuple[pd.Series, dict[str, int]]:
        if not isinstance(prices, pd.Series):
            raise TypeError("prices must be a pandas Series")
        input_count = len(prices)
        if input_count == 0:
            raise ValueError("prices cannot be empty")

        numeric = pd.to_numeric(prices, errors="coerce").to_numpy(dtype=float)
        try:
            parsed_index = pd.to_datetime(prices.index, errors="coerce", utc=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("prices must have a datetime-compatible index") from exc

        valid_dates = ~parsed_index.isna()
        valid_values = np.isfinite(numeric) & (numeric > 0)
        valid = np.asarray(valid_dates) & valid_values
        if not np.any(valid):
            raise ValueError("prices contain no finite, positive, dated observations")

        clean = pd.Series(
            numeric[valid],
            index=pd.DatetimeIndex(parsed_index[valid]).tz_convert(None),
            name=prices.name or "close",
            dtype=float,
        )
        clean = clean[~clean.index.duplicated(keep="last")].sort_index()
        return clean, {
            "input_observations": input_count,
            "dropped_observations": input_count - len(clean),
        }

    def _analyze_scale(
        self,
        log_prices: np.ndarray,
        prices: pd.Series,
        scale: ScaleConfig,
    ) -> dict[str, Any]:
        observation_count = len(prices)
        empty = pd.Series(np.nan, index=prices.index, dtype=float)
        step = max(1, scale.weeks // self.step_divisor)

        if observation_count < scale.weeks:
            return {
                "score": empty.copy(),
                "forecast": empty.copy(),
                "latest_fit": None,
                "diagnostics": {
                    "label": scale.label,
                    "window_weeks": scale.weeks,
                    "endpoint_step": step,
                    "status": "insufficient_history",
                    "observations": observation_count,
                    "required_observations": scale.weeks,
                    "scheduled_fit_count": 0,
                    "successful_fit_count": 0,
                    "qualified_fit_count": 0,
                    "fit_windows": [],
                },
            }

        endpoints = self._endpoint_positions(observation_count, scale.weeks, step)
        recent_qualified: list[bool] = []
        score_by_position: dict[int, float] = {}
        tc_by_position: dict[int, float] = {}
        fits: list[LPPLSFit] = []
        final_fit: LPPLSFit | None = None
        fit_windows: list[dict[str, Any]] = []

        for endpoint_exclusive in endpoints:
            start_position = endpoint_exclusive - scale.weeks
            end_position = endpoint_exclusive - 1
            fit = self._fit_window(
                log_prices[start_position:endpoint_exclusive],
                start_position=start_position,
                end_position=end_position,
            )
            is_qualified = fit is not None and fit.qualified
            recent_qualified.append(is_qualified)
            trailing = recent_qualified[-self.confirmation_lookback :]
            score_by_position[end_position] = float(sum(trailing) / len(trailing))

            window_record: dict[str, Any] = {
                "start_position": start_position,
                "end_position": end_position,
                "start_date": self._iso_date(prices.index[start_position]),
                "end_date": self._iso_date(prices.index[end_position]),
                "status": "fit" if fit is not None else "numerical_failure",
                "qualified": bool(is_qualified),
            }
            if fit is not None:
                fits.append(fit)
                if endpoint_exclusive == observation_count:
                    final_fit = fit
                if fit.qualified:
                    tc_by_position[end_position] = fit.weeks_to_tc
                window_record.update(
                    {
                        "mse": fit.mse,
                        "B": fit.B,
                        "m": fit.m,
                        "omega": fit.omega,
                        "damping": fit.damping,
                        "oscillation_count": fit.oscillation_count,
                        "relative_oscillation_amplitude": (
                            fit.relative_oscillation_amplitude
                        ),
                        "max_relative_error": fit.max_relative_error,
                    }
                )
            fit_windows.append(window_record)

        score_sparse = pd.Series(
            score_by_position.values(),
            index=prices.index[list(score_by_position)],
            dtype=float,
        )
        score = score_sparse.reindex(prices.index).ffill()

        forecast = pd.Series(np.nan, index=prices.index, dtype=float)
        for position, weeks_to_tc in tc_by_position.items():
            forecast.iloc[position] = weeks_to_tc

        qualified_count = sum(fit.qualified for fit in fits)
        return {
            "score": score,
            "forecast": forecast,
            "latest_fit": final_fit,
            "diagnostics": {
                "label": scale.label,
                "window_weeks": scale.weeks,
                "endpoint_step": step,
                "status": "ok" if fits else "no_numerically_stable_fit",
                "observations": observation_count,
                "scheduled_fit_count": len(endpoints),
                "successful_fit_count": len(fits),
                "qualified_fit_count": int(qualified_count),
                "final_endpoint_included": bool(
                    endpoints and endpoints[-1] == observation_count
                ),
                "fit_windows": fit_windows,
            },
        }

    @staticmethod
    def _endpoint_positions(
        observation_count: int, window: int, step: int
    ) -> list[int]:
        """Return exclusive fit endpoints and always include the final row."""

        if observation_count < window:
            return []
        endpoints = list(range(window, observation_count + 1, step))
        if not endpoints or endpoints[-1] != observation_count:
            endpoints.append(observation_count)
        return endpoints

    def _fit_window(
        self,
        log_prices: np.ndarray,
        *,
        start_position: int,
        end_position: int,
    ) -> LPPLSFit | None:
        """Select the stable grid candidate with the lowest log-price MSE."""

        values = np.asarray(log_prices, dtype=float)
        window = len(values)
        if window < _MIN_FIT_OBSERVATIONS or not np.all(np.isfinite(values)):
            return None

        t = np.arange(window, dtype=float)
        maximum_ahead = max(2.0, window * self.max_tc_fraction)
        ahead_grid = np.linspace(1.0, maximum_ahead, self.tc_grid_size)
        tc_grid = (window - 1.0) + ahead_grid
        best: _Candidate | None = None

        for tc in tc_grid:
            dt = tc - t
            if np.any(dt <= 0) or not np.all(np.isfinite(dt)):
                continue
            log_dt = np.log(dt)
            for m in self.m_grid:
                with np.errstate(over="ignore", invalid="ignore"):
                    power = np.power(dt, m)
                if not np.all(np.isfinite(power)):
                    continue
                for omega in self.omega_grid:
                    phase = omega * log_dt
                    design = np.column_stack(
                        (
                            np.ones(window, dtype=float),
                            power,
                            power * np.cos(phase),
                            power * np.sin(phase),
                        )
                    )
                    if not np.all(np.isfinite(design)):
                        continue
                    try:
                        coefficients, _, rank, singular_values = np.linalg.lstsq(
                            design, values, rcond=None
                        )
                    except np.linalg.LinAlgError:
                        continue
                    if rank < design.shape[1] or len(singular_values) < design.shape[1]:
                        continue
                    smallest_singular = float(singular_values[-1])
                    if smallest_singular <= np.finfo(float).eps:
                        continue
                    condition = float(singular_values[0] / smallest_singular)
                    if not np.isfinite(condition) or condition > _MAX_DESIGN_CONDITION:
                        continue

                    fitted = design @ coefficients
                    residual = values - fitted
                    mse = float(np.mean(np.square(residual)))
                    if not np.isfinite(mse):
                        continue
                    if best is None or mse < best.mse:
                        best = _Candidate(
                            tc=float(tc),
                            A=float(coefficients[0]),
                            B=float(coefficients[1]),
                            m=float(m),
                            C1=float(coefficients[2]),
                            C2=float(coefficients[3]),
                            omega=float(omega),
                            mse=mse,
                            fitted_log_prices=fitted.astype(float, copy=True),
                            design_condition=condition,
                        )

        if best is None:
            return None
        return self._qualify_candidate(
            best,
            actual_log_prices=values,
            start_position=start_position,
            end_position=end_position,
        )

    def _qualify_candidate(
        self,
        candidate: _Candidate,
        *,
        actual_log_prices: np.ndarray,
        start_position: int,
        end_position: int,
    ) -> LPPLSFit:
        amplitude = float(np.hypot(candidate.C1, candidate.C2))
        absolute_b = abs(candidate.B)
        damping_denominator = candidate.omega * amplitude
        damping_numerator = candidate.m * absolute_b
        if damping_denominator <= np.finfo(float).eps:
            damping = float("inf") if damping_numerator > 0 else 0.0
        else:
            damping = float(damping_numerator / damping_denominator)

        window = len(actual_log_prices)
        first_distance = candidate.tc
        last_distance = candidate.tc - (window - 1.0)
        if first_distance <= 0 or last_distance <= 0:
            oscillations = 0.0
        else:
            oscillations = float(
                candidate.omega / (2.0 * pi) * np.log(first_distance / last_distance)
            )

        if absolute_b <= np.finfo(float).eps:
            relative_oscillation_amplitude = float("inf") if amplitude > 0 else 0.0
        else:
            relative_oscillation_amplitude = float(amplitude / absolute_b)

        log_ratio = candidate.fitted_log_prices - actual_log_prices
        if not np.all(np.isfinite(log_ratio)) or np.any(log_ratio > 700.0):
            max_relative_error = float("inf")
        else:
            with np.errstate(over="ignore", invalid="ignore"):
                relative_error = np.abs(np.expm1(log_ratio))
            max_relative_error = (
                float(np.max(relative_error))
                if np.all(np.isfinite(relative_error))
                else float("inf")
            )

        passes_b = candidate.B < 0.0
        passes_m = self.filters.m_min < candidate.m < self.filters.m_max
        passes_omega = (
            self.filters.omega_min <= candidate.omega <= self.filters.omega_max
        )
        passes_damping = damping >= self.filters.min_damping
        oscillation_filter_applied = (
            relative_oscillation_amplitude
            >= self.filters.min_relative_oscillation_amplitude
        )
        passes_oscillations = (
            not oscillation_filter_applied
            or oscillations >= self.filters.min_oscillations
        )
        passes_relative_error = max_relative_error <= self.filters.max_relative_error
        qualified = all(
            (
                passes_b,
                passes_m,
                passes_omega,
                passes_damping,
                passes_oscillations,
                passes_relative_error,
            )
        )

        return LPPLSFit(
            start_position=start_position,
            end_position=end_position,
            tc_window_position=candidate.tc,
            tc_absolute_position=start_position + candidate.tc,
            A=candidate.A,
            B=candidate.B,
            m=candidate.m,
            C1=candidate.C1,
            C2=candidate.C2,
            omega=candidate.omega,
            mse=candidate.mse,
            max_relative_error=max_relative_error,
            damping=damping,
            oscillation_count=oscillations,
            relative_oscillation_amplitude=relative_oscillation_amplitude,
            design_condition=candidate.design_condition,
            passes_b_filter=bool(passes_b),
            passes_m_filter=bool(passes_m),
            passes_omega_filter=bool(passes_omega),
            passes_damping_filter=bool(passes_damping),
            passes_oscillation_filter=bool(passes_oscillations),
            oscillation_filter_applied=bool(oscillation_filter_applied),
            passes_max_relative_error_filter=bool(passes_relative_error),
            qualified=bool(qualified),
        )

    @staticmethod
    def _lppls_values(t: np.ndarray, fit: LPPLSFit) -> np.ndarray:
        distance = fit.tc_window_position - np.asarray(t, dtype=float)
        if np.any(distance <= 0) or not np.all(np.isfinite(distance)):
            return np.full_like(distance, np.nan, dtype=float)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            power = np.power(distance, fit.m)
            log_distance = np.log(distance)
            values = (
                fit.A
                + fit.B * power
                + fit.C1 * power * np.cos(fit.omega * log_distance)
                + fit.C2 * power * np.sin(fit.omega * log_distance)
            )
        return np.asarray(values, dtype=float)

    def _fit_curve(self, fit: LPPLSFit, prices: pd.Series) -> pd.Series | None:
        window = fit.end_position - fit.start_position + 1
        fitted_log = self._lppls_values(np.arange(window, dtype=float), fit)
        if not np.all(np.isfinite(fitted_log)):
            return None
        maximum_log = np.log(np.finfo(float).max)
        if np.any(fitted_log > maximum_log):
            return None
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            fitted_prices = np.exp(fitted_log)
        if not np.all(np.isfinite(fitted_prices)):
            return None
        index = prices.index[fit.start_position : fit.end_position + 1]
        return pd.Series(fitted_prices, index=index, name="lppls_fit", dtype=float)

    def _parameter_row(
        self,
        fit: LPPLSFit,
        prices: pd.Series,
        scale: ScaleConfig,
        *,
        latest_ratio: float,
    ) -> dict[str, Any]:
        endpoint = pd.Timestamp(prices.index[fit.end_position])
        critical_time = endpoint + pd.Timedelta(weeks=fit.weeks_to_tc)
        return {
            "model": self.name,
            "scale": scale.label,
            "scale_key": scale.key,
            "horizon_weeks": scale.weeks,
            "status": "qualified" if fit.qualified else "unqualified",
            "estimate_kind": "coarse_grid_candidate",
            "fit_start": self._iso_date(prices.index[fit.start_position]),
            "fit_end": self._iso_date(endpoint),
            "start_position": fit.start_position,
            "end_position": fit.end_position,
            "tc_date": self._iso_date(critical_time),
            "weeks_to_tc": fit.weeks_to_tc,
            "A": fit.A,
            "B": fit.B,
            "m": fit.m,
            "omega": fit.omega,
            "C1": fit.C1,
            "C2": fit.C2,
            "mse": fit.mse,
            "max_relative_error": fit.max_relative_error,
            "damping": fit.damping,
            "oscillation_count": fit.oscillation_count,
            "relative_oscillation_amplitude": fit.relative_oscillation_amplitude,
            "design_condition": fit.design_condition,
            "passes_b_filter": fit.passes_b_filter,
            "passes_m_filter": fit.passes_m_filter,
            "passes_omega_filter": fit.passes_omega_filter,
            "passes_damping_filter": fit.passes_damping_filter,
            "passes_oscillation_filter": fit.passes_oscillation_filter,
            "oscillation_filter_applied": fit.oscillation_filter_applied,
            "passes_max_relative_error_filter": (fit.passes_max_relative_error_filter),
            "qualified": fit.qualified,
            "temporal_persistence_ratio": latest_ratio,
        }

    @staticmethod
    def _iso_date(value: Any) -> str:
        return pd.Timestamp(value).isoformat()


__all__ = ["LPPLSFilterConfig", "LPPLSFit", "LPPLSModel"]

"""Command-line interface for the LPPLS research dashboard."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys
import webbrowser

from .analysis import AnalysisEngine
from .config import (
    DEFAULT_OUTPUT_NAME,
    HISTORICAL_EVENTS,
    INSTRUMENTS,
    SCALES,
    InstrumentConfig,
)
from .dashboard import write_dashboard
from .data import PriceProvider, YahooFinanceProvider, download_unique
from .models.lppls import LPPLSModel
from .models.registry import ModelRegistry


BrowserOpener = Callable[[str], object]


def positive_int(value: str) -> int:
    """Argparse converter for strictly positive integer options."""

    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lppls_test.py",
        description=(
            "Download complete weekly price histories, run the LPPLS model at "
            "three rolling horizons, and write one interactive HTML dashboard."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_NAME),
        help=f"dashboard HTML path (default: {DEFAULT_OUTPUT_NAME})",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="write the dashboard without opening a browser",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        metavar="SYMBOL",
        help="configured ticker subset; accepts spaces and/or commas",
    )
    parser.add_argument(
        "--step-divisor",
        type=positive_int,
        default=4,
        help=(
            "rolling-fit stride divisor (stride=max(1, horizon/divisor)); "
            "larger values are denser and slower (default: 4)"
        ),
    )
    return parser


def parse_tickers(values: Sequence[str] | None) -> tuple[str, ...] | None:
    """Normalize CLI ticker tokens while retaining the requested order."""

    if values is None:
        return None
    parsed: list[str] = []
    seen: set[str] = set()
    for value in values:
        for token in value.split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in seen:
                parsed.append(symbol)
                seen.add(symbol)
    return tuple(parsed)


def select_instruments(
    requested: Sequence[str] | None,
    configured: Sequence[InstrumentConfig] = INSTRUMENTS,
) -> tuple[InstrumentConfig, ...]:
    """Return a configured subset, rejecting unknown ticker symbols."""

    if requested is None:
        return tuple(configured)
    if not requested:
        raise ValueError("At least one ticker is required")

    by_symbol = {instrument.symbol.upper(): instrument for instrument in configured}
    unknown = [symbol for symbol in requested if symbol.upper() not in by_symbol]
    if unknown:
        available = ", ".join(instrument.symbol for instrument in configured)
        raise ValueError(
            f"Unknown configured ticker(s): {', '.join(unknown)}. Available: {available}"
        )

    selected: list[InstrumentConfig] = []
    seen: set[str] = set()
    for symbol in requested:
        normalized = symbol.upper()
        if normalized not in seen:
            selected.append(by_symbol[normalized])
            seen.add(normalized)
    return tuple(selected)


def _print_download_summary(
    instruments: Sequence[InstrumentConfig],
    price_data: dict[str, object],
    errors: dict[str, str],
) -> None:
    for instrument in instruments:
        prices = price_data.get(instrument.symbol)
        if prices is not None:
            first = prices.index[0].date().isoformat()
            latest = prices.index[-1].date().isoformat()
            print(
                f"  ✓ {instrument.symbol:<5} {len(prices):>5} weekly observations "
                f"({first} → {latest})"
            )
        elif instrument.symbol in errors:
            print(
                f"  ! {instrument.symbol:<5} {errors[instrument.symbol]}",
                file=sys.stderr,
            )


def run(
    args: argparse.Namespace,
    *,
    provider: PriceProvider | None = None,
    opener: BrowserOpener | None = None,
) -> int:
    """Execute an already-parsed dashboard run; returns a process status code."""

    requested = parse_tickers(args.tickers)
    selected = select_instruments(requested)
    symbols = ", ".join(instrument.symbol for instrument in selected)

    print("LPPLS Bubble Research Dashboard")
    print(f"Tickers: {symbols}")
    print("Source range: first Yahoo Finance observation through latest available week")
    print(f"Downloading {len(selected)} unique ticker(s)...")

    active_provider = provider if provider is not None else YahooFinanceProvider()
    price_data, download_errors = download_unique(selected, active_provider)
    _print_download_summary(selected, price_data, download_errors)
    if not price_data:
        print("Error: no usable market data was downloaded.", file=sys.stderr)
        return 1

    registry = ModelRegistry()
    registry.register(
        LPPLSModel.key,
        lambda: LPPLSModel(scales=SCALES, step_divisor=args.step_divisor),
    )
    engine = AnalysisEngine(registry.create_many())

    analyses = []
    analysis_errors: dict[str, str] = {}
    print(
        "Analyzing rolling horizons: "
        + ", ".join(f"{scale.key}={scale.weeks}w" for scale in SCALES)
    )
    for instrument in selected:
        if instrument.symbol not in price_data:
            continue
        print(f"  • {instrument.symbol}: fitting...", end="", flush=True)
        try:
            result = engine.run((instrument,), price_data)
        except Exception as exc:  # keep partial dashboard useful when one ticker fails
            analysis_errors[instrument.symbol] = str(exc)
            print(f" failed ({exc})", file=sys.stderr)
            continue
        if result:
            analyses.extend(result)
            print(" done")
        else:
            analysis_errors[instrument.symbol] = "analysis returned no result"
            print(" skipped", file=sys.stderr)

    if not analyses:
        print("Error: every ticker failed during analysis.", file=sys.stderr)
        return 1
    if analysis_errors:
        failed = ", ".join(analysis_errors)
        print(
            f"Warning: dashboard excludes failed ticker(s): {failed}", file=sys.stderr
        )

    try:
        output_path = write_dashboard(analyses, args.output, events=HISTORICAL_EVENTS)
    except Exception as exc:
        print(f"Error: could not write dashboard: {exc}", file=sys.stderr)
        return 1

    output_path = Path(output_path).expanduser().resolve()
    print(f"Dashboard written: {output_path}")
    if not args.no_open:
        browser_opener = opener if opener is not None else webbrowser.open
        try:
            browser_opener(output_path.as_uri())
            print("Opened dashboard in the default browser.")
        except Exception as exc:  # the generated artifact is still a successful result
            print(
                f"Warning: dashboard was saved but browser could not open: {exc}",
                file=sys.stderr,
            )
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    provider: PriceProvider | None = None,
    opener: BrowserOpener | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args, provider=provider, opener=opener)
    except ValueError as exc:
        parser.error(str(exc))
    return 2  # pragma: no cover - parser.error always exits


__all__ = [
    "build_parser",
    "main",
    "parse_tickers",
    "positive_int",
    "run",
    "select_instruments",
]

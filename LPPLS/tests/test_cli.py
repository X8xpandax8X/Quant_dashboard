from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from lppls import cli
from lppls.models.base import BubbleModel
from lppls.types import ModelOutput


def test_parse_and_select_tickers_support_commas_case_and_deduplication() -> None:
    requested = cli.parse_tickers(["nvda, msft", "NVDA"])
    selected = cli.select_instruments(requested)

    assert requested == ("NVDA", "MSFT")
    assert [instrument.symbol for instrument in selected] == ["NVDA", "MSFT"]


def test_select_instruments_reports_unknown_symbol() -> None:
    with pytest.raises(ValueError, match="Unknown configured ticker.*Available"):
        cli.select_instruments(("NOTREAL",))


def test_parser_rejects_nonpositive_step_divisor() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--step-divisor", "0"])


def test_cli_is_offline_filterable_and_opens_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    class Provider:
        def history(self, symbol: str) -> pd.Series:
            calls.append(symbol)
            return pd.Series(
                range(1, 41),
                dtype=float,
                index=pd.date_range("2020-01-05", periods=40, freq="W"),
                name="close",
            )

    class FastModel(BubbleModel):
        key = "lppls"
        name = "Test LPPLS"

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def analyze(self, prices: pd.Series) -> ModelOutput:
            score = pd.DataFrame(
                {"composite": [0.25] * len(prices)}, index=prices.index
            )
            return ModelOutput(self.key, self.name, score)

    written: list[tuple[list[str], Path]] = []

    def fake_write(analyses, output_path, events):
        path = Path(output_path)
        path.write_text("<!doctype html><title>offline test</title>", encoding="utf-8")
        written.append(([item.instrument.symbol for item in analyses], path))
        return path

    monkeypatch.setattr(cli, "LPPLSModel", FastModel)
    monkeypatch.setattr(cli, "write_dashboard", fake_write)
    opened: list[str] = []
    output = tmp_path / "single-dashboard.html"

    status = cli.main(
        ["--tickers", "nvda,MSFT", "--output", str(output)],
        provider=Provider(),
        opener=opened.append,
    )

    assert status == 0
    assert calls == ["NVDA", "MSFT"]
    assert written == [(["NVDA", "MSFT"], output)]
    assert output.is_file()
    assert opened == [output.resolve().as_uri()]


def test_cli_no_open_suppresses_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Provider:
        def history(self, symbol: str) -> pd.Series:
            return pd.Series(
                [1.0, 2.0],
                index=pd.date_range("2024-01-07", periods=2, freq="W"),
                name="close",
            )

    class FastModel(BubbleModel):
        key = "lppls"
        name = "Test LPPLS"

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def analyze(self, prices: pd.Series) -> ModelOutput:
            return ModelOutput(
                self.key,
                self.name,
                pd.DataFrame({"composite": [0.0] * len(prices)}, index=prices.index),
            )

    def fake_write(analyses, output_path, events):
        path = Path(output_path)
        path.write_text("ok", encoding="utf-8")
        return path

    monkeypatch.setattr(cli, "LPPLSModel", FastModel)
    monkeypatch.setattr(cli, "write_dashboard", fake_write)
    opened: list[str] = []

    status = cli.main(
        ["--tickers", "CSCO", "--output", str(tmp_path / "out.html"), "--no-open"],
        provider=Provider(),
        opener=opened.append,
    )

    assert status == 0
    assert opened == []

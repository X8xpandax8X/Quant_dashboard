from __future__ import annotations

from lppls.config import (
    GROUP_INDIVIDUAL_STOCK,
    GROUP_MARKET_INDEX,
    GROUP_SP500_SECTOR,
    INDIVIDUAL_STOCKS,
    INSTRUMENTS,
    MARKET_INDICES,
    SP500_SECTORS,
)


def test_config_has_three_indices_eleven_sectors_and_a_separate_stock_universe() -> (
    None
):
    assert {instrument.symbol for instrument in MARKET_INDICES} == {
        "^GSPC",
        "^IXIC",
        "^DJI",
    }
    assert {instrument.group for instrument in MARKET_INDICES} == {GROUP_MARKET_INDEX}

    assert len(SP500_SECTORS) == 11
    assert {instrument.name for instrument in SP500_SECTORS} == {
        "Information Technology",
        "Communication Services",
        "Consumer Discretionary",
        "Consumer Staples",
        "Financials",
        "Health Care",
        "Industrials",
        "Energy",
        "Materials",
        "Utilities",
        "Real Estate",
    }
    assert {instrument.group for instrument in SP500_SECTORS} == {GROUP_SP500_SECTOR}

    assert INDIVIDUAL_STOCKS
    assert {instrument.group for instrument in INDIVIDUAL_STOCKS} == {
        GROUP_INDIVIDUAL_STOCK
    }
    assert INSTRUMENTS == MARKET_INDICES + SP500_SECTORS + INDIVIDUAL_STOCKS
    assert len({instrument.symbol for instrument in INSTRUMENTS}) == len(INSTRUMENTS)

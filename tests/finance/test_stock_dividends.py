import pandas as pd

from zipline.assets import Equity, ExchangeInfo
from zipline.data.adjustments import StockDividend
from zipline.finance.ledger import PositionTracker
from zipline.finance.position import Position


def _asset():
    return Equity(1, exchange_info=ExchangeInfo("NYSE", "NYSE", "US"))


def _dividend(asset, ratio=0.15):
    return StockDividend(
        asset,
        asset,
        ratio,
        pd.Timestamp("2020-01-06", tz="UTC"),
    )


def test_long_stock_dividend_drops_fractional_share():
    asset = _asset()
    position = Position(asset, amount=10, cost_basis=10.0, last_sale_price=10.0)

    owed = position.earn_stock_dividend(_dividend(asset))

    assert owed["payment_asset"] == asset
    assert owed["share_count"] == 1


def test_short_stock_dividend_rounds_shares_owed_toward_zero():
    """10 shares short and a 0.15 ratio is -1.5 shares. Owe 1, not 2."""
    asset = _asset()
    position = Position(asset, amount=-10, cost_basis=10.0, last_sale_price=10.0)

    owed = position.earn_stock_dividend(_dividend(asset))

    assert owed["share_count"] == -1


def test_stock_dividend_is_paid_once_and_dirties_position_stats():
    asset = _asset()
    pay_date = pd.Timestamp("2020-01-06", tz="UTC")
    tracker = PositionTracker("daily")
    tracker.update_position(
        asset,
        amount=100,
        last_sale_price=10.0,
        cost_basis=10.0,
    )
    # Populate and clear the stats cache.
    assert tracker.stats.net_value == 1000
    assert tracker._dirty_stats is False

    tracker._unpaid_stock_dividends[pay_date] = [
        {"payment_asset": asset, "share_count": 10}
    ]

    assert tracker.pay_dividends(pay_date) == 0.0
    assert tracker.positions[asset].amount == 110
    assert pay_date not in tracker._unpaid_stock_dividends
    assert tracker._dirty_stats is True

    # A second call for the same pay date must not credit the shares again.
    tracker.pay_dividends(pay_date)
    assert tracker.positions[asset].amount == 110
    assert tracker.stats.net_value == 1100

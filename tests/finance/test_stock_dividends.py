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


class _PriceSource:
    """Just enough of a DataPortal for ``sync_last_sale_prices``."""

    def __init__(self, prices):
        self.prices = prices

    def get_scalar_asset_spot_value(self, asset, field, dt, data_frequency):
        return self.prices[asset]


def test_spin_off_stock_dividend_opens_position_and_dirties_position_stats():
    """A stock dividend paid in another asset opens a new position.

    The new position has no price until the next ``sync_last_sale_prices``,
    so it is valued at 0.0 for that bar. The stats cache still has to be
    recomputed so the new position shows up.
    """
    parent = _asset()
    spin_off = Equity(2, exchange_info=ExchangeInfo("NYSE", "NYSE", "US"))
    pay_date = pd.Timestamp("2020-01-06", tz="UTC")
    tracker = PositionTracker("daily")
    tracker.update_position(
        parent,
        amount=100,
        last_sale_price=10.0,
        cost_basis=10.0,
    )
    tracker.earn_dividends(
        [],
        [StockDividend(parent, spin_off, 0.15, pay_date)],
    )
    # Populate and clear the stats cache.
    assert tracker.stats.net_value == 1000
    assert tracker._dirty_stats is False

    assert tracker.pay_dividends(pay_date) == 0.0

    assert spin_off in tracker.positions
    new_position = tracker.positions[spin_off]
    assert new_position.amount == 15
    assert new_position.last_sale_price == 0.0
    assert tracker.positions[parent].amount == 100
    assert pay_date not in tracker._unpaid_stock_dividends
    assert tracker._dirty_stats is True

    stats = tracker.stats
    assert sorted(stats.position_exposure_series.index) == [1, 2]
    # Unpriced until the next sync, so the new shares add nothing yet.
    assert stats.net_value == 1000

    tracker.sync_last_sale_prices(
        pay_date,
        _PriceSource({parent: 10.0, spin_off: 4.0}),
    )
    assert tracker.stats.net_value == 1000 + 15 * 4.0


def test_stock_dividend_under_one_share_is_not_booked():
    """0.15 x 1 short share truncates to -0.0. Nothing to pay, so no entry."""
    parent = _asset()
    spin_off = Equity(2, exchange_info=ExchangeInfo("NYSE", "NYSE", "US"))
    pay_date = pd.Timestamp("2020-01-06", tz="UTC")
    tracker = PositionTracker("daily")
    tracker.update_position(
        parent,
        amount=-1,
        last_sale_price=10.0,
        cost_basis=10.0,
    )

    tracker.earn_dividends(
        [],
        [StockDividend(parent, spin_off, 0.15, pay_date)],
    )

    assert pay_date not in tracker._unpaid_stock_dividends
    assert tracker.stats.net_value == -10
    tracker.pay_dividends(pay_date)
    assert spin_off not in tracker.positions
    assert tracker._dirty_stats is False
    assert tracker.positions[parent].amount == -1

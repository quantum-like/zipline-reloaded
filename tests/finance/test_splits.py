import pandas as pd

from zipline.assets import Equity, ExchangeInfo
from zipline.finance.ledger import Ledger
from zipline.finance.order import Order
from zipline.finance.position import Position


def _asset():
    return Equity(1, exchange_info=ExchangeInfo("NYSE", "NYSE", "US"))


def test_long_split_drops_fractional_share_for_cash():
    """A 1-for-3 reverse split of 100 shares stays 33 shares plus cash."""
    asset = _asset()
    position = Position(asset, amount=100, cost_basis=30.0, last_sale_price=30.0)

    cash = position.handle_split(asset, 3)

    assert position.amount == 33
    assert position.cost_basis == 90.0
    assert cash == 30.0


def test_short_split_rounds_toward_zero_and_charges_cash():
    """A short reverse split must not grow the short by rounding away from zero.

    100 shares short at $30, 1-for-3, is -33.333 shares. The whole-share
    position is -33, and the fractional share is bought back for cash.
    """
    asset = _asset()
    position = Position(asset, amount=-100, cost_basis=30.0, last_sale_price=30.0)

    cash = position.handle_split(asset, 3)

    assert position.amount == -33
    assert position.cost_basis == 90.0
    assert cash == -30.0


def test_ledger_applies_negative_split_cash_for_shorts():
    asset = _asset()
    sessions = pd.date_range("2020-01-02", periods=2, tz="UTC")
    ledger = Ledger(sessions, 100_000, "daily")
    ledger.position_tracker.update_position(
        asset,
        amount=-100,
        cost_basis=30.0,
        last_sale_price=30.0,
    )

    ledger.process_splits([(asset, 3)])

    assert ledger.position_tracker.positions[asset].amount == -33
    assert ledger.portfolio.cash == 100_000 - 30


def test_partial_buy_split_scales_filled_shares():
    asset = _asset()
    order = Order(
        dt=pd.Timestamp("2020-01-02", tz="UTC"),
        asset=asset,
        amount=100,
    )
    order.filled = 40

    order.handle_split(0.5)  # 2-for-1

    assert order.amount == 200
    assert order.filled == 80
    assert order.open_amount == 120
    assert order.direction == 1


def test_partial_short_reverse_split_scales_filled_shares():
    asset = _asset()
    order = Order(
        dt=pd.Timestamp("2020-01-02", tz="UTC"),
        asset=asset,
        amount=-100,
    )
    order.filled = -40

    order.handle_split(3)  # 1-for-3

    assert order.amount == -33
    assert order.filled == -13
    assert order.open_amount == -20
    assert order.direction == -1

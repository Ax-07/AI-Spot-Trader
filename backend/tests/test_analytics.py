from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from ai_spot_trader.analytics.paper import (
    PaperAnalyticsCycleFact,
    PaperAnalyticsDataError,
    build_paper_analytics_report,
)

BASE = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def _portfolio(*, cash: str, btc: str = "0", offset: int) -> dict[str, object]:
    positions: list[dict[str, object]] = []
    if Decimal(btc) != 0:
        positions.append({"asset": "BTC", "quantity": btc, "available": btc})
    return {
        "portfolio_state_id": str(UUID(int=10_000 + offset)),
        "as_of": (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "mode": "PAPER",
        "balances": [{"asset": "EUR", "available": cash}],
        "positions": positions,
    }


def _agent_input(
    cycle_id: UUID,
    *,
    price: str,
    portfolio: dict[str, object],
    offset: int,
) -> dict[str, object]:
    at = BASE + timedelta(minutes=offset)
    return {
        "cycle_id": str(cycle_id),
        "created_at": at.isoformat().replace("+00:00", "Z"),
        "market_state": {
            "market_state_id": str(UUID(int=20_000 + offset)),
            "as_of": at.isoformat().replace("+00:00", "Z"),
            "symbol": "BTC/EUR",
            "last_price": price,
            "context": None,
        },
        "portfolio_state": portfolio,
        "aggressiveness": 5,
    }


def _decision(
    cycle_id: UUID, *, action: str, quantity: str | None, offset: int
) -> dict[str, object]:
    return {
        "decision_id": str(UUID(int=30_000 + offset)),
        "cycle_id": str(cycle_id),
        "created_at": (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "action": action,
        "symbol": "BTC/EUR",
        "proposed_quantity": quantity,
        "rationale": "test",
    }


def _risk(
    cycle_id: UUID,
    *,
    status: str,
    requested: str | None,
    authorized: str | None,
    offset: int,
) -> dict[str, object]:
    reasons: list[str] = []
    if status == "REJECT":
        reasons = ["MAX_ORDER_NOTIONAL_EXCEEDED"]
    elif status == "MODIFY":
        reasons = ["MAX_ORDER_NOTIONAL_LIMIT"]
    elif requested is None:
        reasons = ["HOLD_NO_EXECUTION"]
    return {
        "risk_assessment_id": str(UUID(int=40_000 + offset)),
        "cycle_id": str(cycle_id),
        "decision_id": str(UUID(int=30_000 + offset)),
        "assessed_at": (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"),
        "status": status,
        "requested_quantity": requested,
        "authorized_quantity": authorized,
        "evaluated_limits": [],
        "reasons": reasons,
    }


def _fill(
    cycle_id: UUID,
    *,
    action: str,
    quantity: str,
    reference: str,
    price: str,
    fee: str,
    spread: str,
    slippage: str,
    offset: int,
) -> dict[str, object]:
    quantity_decimal = Decimal(quantity)
    notional = Decimal(price) * quantity_decimal
    at = BASE + timedelta(minutes=offset)
    return {
        "fill_id": str(UUID(int=60_000 + offset)),
        "execution_id": str(UUID(int=50_000 + offset)),
        "market_state_id": str(UUID(int=20_000 + offset)),
        "filled_at": at.isoformat().replace("+00:00", "Z"),
        "pricing_as_of": at.isoformat().replace("+00:00", "Z"),
        "action": action,
        "symbol": "BTC/EUR",
        "quantity": quantity,
        "reference_price": reference,
        "price": price,
        "notional": str(notional),
        "fee": fee,
        "spread_cost": spread,
        "slippage_cost": slippage,
    }


def _fact(
    n: int,
    *,
    status: str = "COMPLETED",
    price: str | None = None,
    before: dict[str, object] | None = None,
    action: str | None = None,
    risk_status: str | None = None,
    proposed: str | None = None,
    authorized: str | None = None,
    fill: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    day_offset: int = 0,
) -> PaperAnalyticsCycleFact:
    cycle_id = UUID(int=n)
    offset = n + day_offset * 1440
    agent = None if price is None or before is None else _agent_input(
        cycle_id, price=price, portfolio=before, offset=offset
    )
    decision = None if action is None else _decision(
        cycle_id, action=action, quantity=proposed, offset=offset
    )
    risk = None
    if risk_status is not None:
        risk = _risk(
            cycle_id,
            status=risk_status,
            requested=proposed,
            authorized=authorized,
            offset=offset,
        )
    if fill is not None:
        fill = dict(fill)
        fill["market_state_id"] = str(UUID(int=20_000 + offset))
        fill["filled_at"] = (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")
        fill["pricing_as_of"] = fill["filled_at"]
        fill["execution_id"] = str(UUID(int=50_000 + offset))
        fill["fill_id"] = str(UUID(int=60_000 + offset))
    if after is not None:
        after = dict(after)
        after["as_of"] = (BASE + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")
    return PaperAnalyticsCycleFact(
        cycle_id=cycle_id,
        status=status,
        recorded_at=BASE + timedelta(minutes=offset),
        result_digest=f"{n:064x}",
        agent_input_payload=agent,
        decision_payload=decision,
        risk_assessment_payload=risk,
        fill_payloads=() if fill is None else (fill,),
        portfolio_after_payload=after,
    )


def _scenario() -> tuple[PaperAnalyticsCycleFact, ...]:
    p0 = _portfolio(cash="1000", offset=1)
    p1 = _portfolio(cash="1000", offset=2)
    p2 = _portfolio(cash="1000", offset=3)
    buy_after = _portfolio(cash="897.99", btc="1", offset=4)
    sell_half_after = _portfolio(cash="942.045", btc="0.5", offset=6)
    sell_all_after = _portfolio(cash="991.050", offset=7 + 1440)

    buy_fill = _fill(
        UUID(int=3), action="BUY", quantity="1", reference="100", price="101",
        fee="1.01", spread="0.5", slippage="0.5", offset=3
    )
    sell_half_fill = _fill(
        UUID(int=5), action="SELL", quantity="0.5", reference="90", price="89",
        fee="0.445", spread="0.25", slippage="0.25", offset=5
    )
    sell_all_fill = _fill(
        UUID(int=7), action="SELL", quantity="0.5", reference="100", price="99",
        fee="0.495", spread="0.25", slippage="0.25", offset=7 + 1440
    )

    return (
        _fact(1, price="100", before=p0, action="HOLD", risk_status="ALLOW"),
        _fact(
            2, price="100", before=p1, action="BUY", risk_status="REJECT",
            proposed="1", authorized=None
        ),
        _fact(
            3, price="100", before=p2, action="BUY", risk_status="ALLOW",
            proposed="1", authorized="1", fill=buy_fill, after=buy_after
        ),
        _fact(
            4, price="120", before=buy_after, action="HOLD", risk_status="ALLOW"
        ),
        _fact(
            5, price="90", before=buy_after, action="SELL", risk_status="MODIFY",
            proposed="1", authorized="0.5", fill=sell_half_fill, after=sell_half_after
        ),
        _fact(6, status="FAILED", price="80", before=sell_half_after),
        _fact(
            7, price="100", before=sell_half_after, action="SELL", risk_status="ALLOW",
            proposed="0.5", authorized="0.5", fill=sell_all_fill, after=sell_all_after,
            day_offset=1,
        ),
    )


def test_empty_analytics_are_deterministic() -> None:
    first = build_paper_analytics_report(())
    second = build_paper_analytics_report(())
    assert first == second
    assert first.summary.initial_equity is None
    assert first.summary.trade_count == 0
    assert first.points == ()
    assert first.daily == ()


def test_paper_analytics_cover_pnl_costs_drawdown_exposure_and_outcomes() -> None:
    report = build_paper_analytics_report(_scenario())
    summary = report.summary

    assert summary.initial_equity == Decimal("1000")
    assert summary.ending_equity == Decimal("991.050")
    assert summary.net_pnl == Decimal("-8.950")
    assert summary.fees == Decimal("1.950")
    assert summary.spread_cost == Decimal("1.00")
    assert summary.slippage_cost == Decimal("1.00")
    assert summary.gross_pnl == Decimal("-5.000")
    assert summary.trade_count == 3
    assert summary.buy_trade_count == 1
    assert summary.sell_trade_count == 2
    assert summary.hold_count == 2
    assert summary.reject_count == 1
    assert summary.modify_count == 1
    assert summary.completed_cycle_count == 6
    assert summary.failed_cycle_count == 1
    assert summary.valued_cycle_count == 7

    buy_point = report.points[2]
    assert buy_point.net_pnl == Decimal("-2.01")
    assert buy_point.gross_pnl == Decimal("0.00")
    assert buy_point.exposure_value == Decimal("100")

    high_point = report.points[3]
    assert high_point.equity == Decimal("1017.99")
    assert high_point.net_pnl == Decimal("17.99")
    assert high_point.gross_pnl == Decimal("20.00")

    failed_point = report.points[5]
    assert failed_point.status == "FAILED"
    assert failed_point.equity == Decimal("982.045")
    assert failed_point.trade_count == 2
    assert summary.max_drawdown_value == Decimal("35.945")
    assert summary.current_exposure_value == Decimal("0")
    assert summary.current_exposure_fraction == Decimal("0")


def test_daily_and_cumulative_performance_use_utc_boundaries() -> None:
    report = build_paper_analytics_report(_scenario())
    assert len(report.daily) == 2
    first_day, second_day = report.daily
    assert first_day.day.isoformat() == "2026-09-20"
    assert first_day.closing_equity == Decimal("982.045")
    assert first_day.daily_net_pnl == Decimal("-17.955")
    assert first_day.trade_count == 2
    assert second_day.day.isoformat() == "2026-09-21"
    assert second_day.closing_equity == Decimal("991.050")
    assert second_day.daily_net_pnl == Decimal("9.005")
    assert second_day.trade_count == 1


def test_replay_is_order_independent_and_has_no_lookahead() -> None:
    facts = _scenario()
    forward = build_paper_analytics_report(facts)
    reverse = build_paper_analytics_report(tuple(reversed(facts)))
    assert forward == reverse
    assert forward.points[0].reference_price == Decimal("100")
    assert forward.points[0].equity == Decimal("1000")
    assert forward.points[3].reference_price == Decimal("120")
    assert forward.source_digest == reverse.source_digest


def test_failed_cycle_without_durable_market_is_counted_but_not_valued() -> None:
    failed = _fact(1, status="FAILED")
    report = build_paper_analytics_report((failed,))
    assert report.summary.failed_cycle_count == 1
    assert report.summary.valued_cycle_count == 0
    assert report.points == ()


def test_broken_portfolio_continuity_is_rejected() -> None:
    first = _fact(
        1,
        price="100",
        before=_portfolio(cash="1000", offset=1),
        action="HOLD",
        risk_status="ALLOW",
    )
    second = _fact(
        2,
        price="100",
        before=_portfolio(cash="999", offset=2),
        action="HOLD",
        risk_status="ALLOW",
    )
    with pytest.raises(PaperAnalyticsDataError, match="continuity"):
        build_paper_analytics_report((first, second))

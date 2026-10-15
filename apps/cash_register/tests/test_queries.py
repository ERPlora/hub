"""Read operations of the cash register app (F01, F02, F03, F07, F11, F12): READ ONLY, paginated with a
stable order, and the blind count applied to every reading. The sale lines are test_integration_sale.py."""

import pytest
from live.errors import NotFound, PermissionDenied

from apps.cash_register.queries import DENOMINATIONS, count_total, currency_decimals
from apps.cash_register.tests.conftest import ctx_for, open_session, run

pytestmark = pytest.mark.django_db


def close(closing_balance: int = 10000, **more):
    return run(
        "cash_register.session.close", {"closing_balance": closing_balance, **more}
    )


# ── Settings, drawers and currency ─────────────────────────────────────────────────────────────


def test_without_a_save_the_factory_settings_are_read():
    read = run("cash_register.settings.get")
    assert read.model_dump() == {
        "enable_cash_register": True,
        "require_opening_balance": False,
        "require_closing_balance": True,
        "allow_negative_balance": False,
        "require_blind_count": False,
        "auto_close_enabled": False,
        "auto_close_time": "04:00",
        "updated_at": None,
    }
    # Every till user reads them (the employee too).
    assert run(
        "cash_register.settings.get", {}, ctx_for("hub_employee")
    ).require_closing_balance


def test_drawers_are_listed_by_name_with_search_and_the_active_filter():
    for name in ("Terrace", "Bar", "Back room"):
        run("cash_register.register.create", {"name": name})
    run(
        "cash_register.register.update",
        {"register_name": "Back room", "is_active": False},
    )
    page = run("cash_register.register.list")
    assert [r.name for r in page.rows] == ["Back room", "Bar", "Terrace"]
    assert [
        r.name for r in run("cash_register.register.list", {"is_active": True}).rows
    ] == ["Bar", "Terrace"]
    assert [
        r.name for r in run("cash_register.register.list", {"search": "ba"}).rows
    ] == ["Back room", "Bar"]


def test_the_currency_of_the_business_with_its_notes_and_coins():
    currency = run("cash_register.currency.get")
    assert (currency.currency, currency.decimals) == ("EUR", 2)
    assert currency.bills == ["500", "200", "100", "50", "20", "10", "5"]
    assert currency.coins == ["2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"]


def test_a_count_adds_up_with_the_decimals_of_its_currency():
    # The eighteen currencies of the product, each with the decimals babel knows.
    assert len(DENOMINATIONS) == 18
    assert (
        currency_decimals("EUR"),
        currency_decimals("JPY"),
        currency_decimals("KWD"),
    ) == (2, 0, 3)
    assert count_total({"bills": {"1000": 5}, "coins": {"1": 3}}, "JPY") == 5003
    assert count_total({"bills": {"0.25": 2}, "coins": {"0.005": 3}}, "KWD") == 515
    assert count_total({"bills": {"50": 2}, "coins": {"0.05": 3}}, "EUR") == 10015
    assert count_total({"bills": {"20000": 2}, "coins": {"10": 3}}, "CLP") == 40030
    assert count_total({"bills": {"2": 3}, "coins": {"1": 4, "0.25": 2}}, "BRL") == 1050


# ── Sessions ───────────────────────────────────────────────────────────────────────────────────


def test_sessions_come_newest_first_with_the_live_expected_of_the_open_one():
    first = open_session(10000)
    close(9990)
    second = open_session(5000)
    run("cash_register.movement.add", {"type": "in", "amount": 700})
    page = run("cash_register.session.list")
    assert [row.id for row in page.rows] == [second.id, first.id]
    assert page.total == 2 and page.limit == 50
    open_row, closed_row = page.rows
    assert (
        open_row.status,
        open_row.expected_balance,
        open_row.closing_balance,
        open_row.difference,
    ) == (
        "open",
        5700,
        None,
        None,
    )
    # A closed session shows its frozen figures.
    assert (
        closed_row.expected_balance,
        closed_row.closing_balance,
        closed_row.difference,
    ) == (10000, 9990, -10)


def test_sessions_are_searched_by_number_and_filtered():
    first = open_session(10000)
    close(9990)
    open_session(5000)
    assert [
        r.number
        for r in run("cash_register.session.list", {"search": first.number[-4:]}).rows
    ] == [first.number]
    assert [
        r.number
        for r in run("cash_register.session.list", {"number": first.number}).rows
    ] == [first.number]
    assert [
        r.status for r in run("cash_register.session.list", {"status": "closed"}).rows
    ] == ["closed"]
    assert [
        r.id for r in run("cash_register.session.list", {"difference_max": -1}).rows
    ] == [first.id]
    assert [
        r.opening_balance
        for r in run("cash_register.session.list", {"opening_min": 6000}).rows
    ] == [10000]
    page = run(
        "cash_register.session.list",
        {"sort": "opening_balance", "dir": "asc", "limit": 1},
    )
    assert [r.opening_balance for r in page.rows] == [5000] and page.total == 2


def test_the_current_session_says_whether_the_drawer_is_on_and_open():
    current = run("cash_register.session.current")
    assert (current.required, current.session) == (True, None)
    session = open_session()
    assert run("cash_register.session.current").session.id == session.id
    run("cash_register.settings.update", {"enable_cash_register": False})
    assert run("cash_register.session.current").required is False


def test_a_session_is_read_by_its_number_with_its_summary_and_notes():
    session = open_session(10000, opening_notes="Morning")
    run("cash_register.movement.add", {"type": "in", "amount": 2000})
    run("cash_register.movement.add", {"type": "out", "amount": 500})
    run(
        "cash_register.movement.add",
        {"type": "out", "amount": 900, "method_type": "card"},
    )
    read = run("cash_register.session.get", {"session": session.number})
    assert read.opening_notes == "Morning"
    assert read.summary.model_dump() == {
        "movement_count": 3,
        "opening_balance": 10000,
        "total_sales": 0,
        "cash_sales": 0,
        "card_sales": 0,
        "other_sales": 0,
        "total_refunds": 0,
        "total_cash_in": 2000,
        "total_cash_out": 1400,
        "total_gifts": 0,
        "expected_cash": 11500,
        "counted": None,
        "difference": None,
    }
    closed = close(11500, closing_notes="ok")
    read = run("cash_register.session.get", {"session_id": str(closed.id)})
    assert (
        read.closing_notes,
        read.summary.counted,
        read.summary.difference,
        read.summary.expected_cash,
    ) == (
        "ok",
        11500,
        0,
        11500,
    )


def test_an_unknown_session_is_not_found():
    with pytest.raises(NotFound) as refused:
        run("cash_register.session.get", {"session": "S-990101-0001"})
    assert refused.value.code == "cash_register.session_not_found"


# ── CASH_REGISTER-F07 Blind count ──────────────────────────────────────────────────────────────


def test_a_blind_count_hides_the_expected_of_the_open_session_from_the_cashier_only():
    run("cash_register.settings.update", {"require_blind_count": True})
    session = open_session(10000)
    employee, manager = ctx_for("hub_employee"), ctx_for("hub_manager")

    row = run("cash_register.session.list", {}, employee).rows[0]
    assert (row.expected_balance, row.expected_hidden) == (None, True)
    assert (
        run("cash_register.session.current", {}, employee).session.expected_balance
        is None
    )
    summary = run(
        "cash_register.session.get", {"session_id": str(session.id)}, employee
    ).summary
    assert (
        summary.expected_cash,
        summary.cash_sales,
        summary.card_sales,
        summary.other_sales,
    ) == (
        None,
        None,
        None,
        None,
    )
    # The supervisor sees it everywhere: the table, the current session and the detail.
    assert (
        run("cash_register.session.list", {}, manager).rows[0].expected_balance == 10000
    )
    assert (
        run("cash_register.session.current", {}, manager).session.expected_balance
        == 10000
    )
    assert (
        run(
            "cash_register.session.get", {"session_id": str(session.id)}, manager
        ).summary.expected_cash
        == 10000
    )

    # Once the count is declared there is nothing left to hide.
    close(10000)
    row = run("cash_register.session.list", {}, employee).rows[0]
    assert (row.expected_balance, row.expected_hidden) == (10000, False)


def test_the_negative_balance_rule_reads_the_real_expected_in_a_blind_count():
    run("cash_register.settings.update", {"require_blind_count": True})
    open_session(1000)
    from live.errors import Conflict

    with pytest.raises(Conflict):
        run(
            "cash_register.movement.add",
            {"type": "out", "amount": 1001},
            ctx_for("hub_employee"),
        )


# ── Movements and counts ───────────────────────────────────────────────────────────────────────


def test_the_lines_of_a_session_newest_first_searched_and_filtered():
    session = open_session()
    run(
        "cash_register.movement.add",
        {"type": "in", "amount": 2000, "description": "Change from the safe"},
    )
    run(
        "cash_register.movement.add",
        {"type": "out", "amount": 500, "description": "Bread supplier"},
    )
    run(
        "cash_register.movement.add",
        {"type": "out", "amount": 300, "method_type": "card"},
    )
    page = run("cash_register.movement.list", {"session": session.number})
    assert [(row.type, row.signed_amount) for row in page.rows] == [
        ("out", -300),
        ("out", -500),
        ("in", 2000),
    ]
    assert page.total == 3
    assert [
        r.description
        for r in run(
            "cash_register.movement.list",
            {"session_id": str(session.id), "search": "bread"},
        ).rows
    ] == ["Bread supplier"]
    assert [
        r.amount
        for r in run(
            "cash_register.movement.list", {"session_id": str(session.id), "type": "in"}
        ).rows
    ] == [2000]
    assert [
        r.method_type
        for r in run(
            "cash_register.movement.list",
            {"session_id": str(session.id), "method_type": "card"},
        ).rows
    ] == ["card"]
    page = run(
        "cash_register.movement.list",
        {
            "session_id": str(session.id),
            "sort": "amount",
            "dir": "asc",
            "limit": 2,
            "offset": 1,
        },
    )
    assert [r.amount for r in page.rows] == [500, 2000] and page.total == 3


def test_the_counts_of_a_session_newest_first():
    session = open_session()
    run("cash_register.count.add", {"type": "opening", "total": 10000})
    run("cash_register.count.add", {"total": 12000})
    page = run("cash_register.count.list", {"session": session.number})
    assert [(c.type, c.total) for c in page.rows] == [
        ("closing", 12000),
        ("opening", 10000),
    ]


def test_every_reading_needs_its_permission():
    from live.context import OperationContext

    from apps.cash_register.tests.conftest import A

    nobody = OperationContext(scope=A, actor="x", permissions=frozenset())
    for name, data in (
        ("cash_register.session.list", {}),
        ("cash_register.session.current", {}),
        ("cash_register.movement.list", {"unassigned": True}),
        ("cash_register.count.list", {"session": "S-990101-0001"}),
        ("cash_register.currency.get", {}),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, nobody)


def test_a_blind_count_hides_the_sale_lines_and_the_totals_of_the_open_session_from_the_cashier(coffee):
    from apps.cash_register.tests.conftest import charge

    run("cash_register.settings.update", {"require_blind_count": True})
    session = open_session(10000)
    charge("2")
    run("cash_register.movement.add", {"type": "out", "amount": 500, "description": "Bread"})
    employee, manager = ctx_for("hub_employee"), ctx_for("hub_manager")
    query = {"session_id": str(session.id)}

    # The cashier sees the float and what was written by hand, never the sales nor any total.
    seen = run("cash_register.movement.list", query, employee)
    assert [(row.type, row.description) for row in seen.rows] == [("out", "Bread")]
    assert run("cash_register.movement.list", {**query, "method_type": "cash"}, employee).total == 1
    figures = run("cash_register.session.get", query, employee).summary
    assert figures.opening_balance == 10000 and figures.movement_count == 1
    for hidden in ("total_sales", "total_refunds", "total_cash_in", "total_cash_out", "total_gifts", "cash_sales", "expected_cash"):
        assert getattr(figures, hidden) is None, hidden

    # The supervisor sees everything.
    assert run("cash_register.movement.list", query, manager).total == 2
    figures = run("cash_register.session.get", query, manager).summary
    assert (figures.total_sales, figures.total_cash_out, figures.expected_cash) == (300, 500, 9800)

    # Once closed, there is nothing left to hide.
    run("cash_register.session.close", {"closing_balance": 9800})
    assert run("cash_register.movement.list", query, employee).total == 2

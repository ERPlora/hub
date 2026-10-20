"""The drawer against the real sale app (CASH_REGISTER-F09, F13, F14, F15, F17): sales charged, voided and
refunded through sale's own operations, and what the shift says about them. No mocks.

The sale lines of an open shift are read from sale at the moment of looking; the close copies them into
the session, so a closed shift never moves again (whatever sale does afterwards).
"""

import datetime as dt

import pytest
from django.utils import timezone

from apps.cash_register.models import Movement, Session
from live.errors import Conflict

from apps.cash_register.tests.conftest import charge, drawer_lock_off, open_session, refund, run, void
from apps.sale.models import PaymentMethod, Sale

pytestmark = pytest.mark.django_db


def summary(session):
    return run("cash_register.session.get", {"session_id": str(session.id)}).summary


def lines(session):
    return run(
        "cash_register.movement.list",
        {"session_id": str(session.id), "dir": "asc", "sort": "created_at"},
    ).rows


def close(closing_balance: int, **more):
    return run(
        "cash_register.session.close", {"closing_balance": closing_balance, **more}
    )


@pytest.fixture
def shirt(db):
    """A 121.00 € product (VAT included), SKU ``SHIRT``."""
    from live.context import system_context

    from apps.cash_register.tests.conftest import A

    return run(
        "inventory.product.create",
        {
            "name": "Shirt",
            "sku": "SHIRT",
            "price": 12100,
            "cost": 4000,
            "tax_category_key": "product.generic",
        },
        system_context(A),
    )


def card_method():
    return PaymentMethod.objects.get(is_system=True, type="card")


def cash_method():
    return PaymentMethod.objects.get(is_system=True, type="cash")


# ── F13: every charge of a sale ────────────────────────────────────────────────────────────────


def test_a_cash_sale_is_in_the_shift_for_what_it_covered_not_what_was_handed_over(
    coffee,
):
    session = open_session(10000)
    sale = charge("2", payments=[{"method": "cash", "tendered": 5000}])
    (line,) = lines(session)
    assert (
        line.type,
        line.amount,
        line.method_type,
        line.sale_id,
        line.sale_number,
    ) == (
        "sale",
        300,
        "cash",
        sale.id,
        sale.number,
    )
    assert line.document_type == "ticket" and line.key == f"sale-{sale.payments[0].id}"
    assert summary(session).expected_cash == 10300
    assert run("cash_register.session.current").session.expected_balance == 10300


def test_a_mixed_payment_leaves_one_line_per_tender_and_only_the_cash_in_the_drawer(
    shirt,
):
    session = open_session(0)
    # The product's own case (cash_register#59): 121.00 € = 50.00 € by card + 71.00 € in cash (90.00 handed over).
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "mixed-payment-0001",
            "lines": [{"product": "SHIRT"}],
            "payments": [
                {"method": "card", "amount": 5000},
                {"method": "cash", "amount": 7100, "tendered": 9000},
            ],
        },
    )
    assert sorted((line.method_type, line.amount) for line in lines(session)) == [
        ("card", 5000),
        ("cash", 7100),
    ]
    figures = summary(session)
    assert (
        figures.total_sales,
        figures.cash_sales,
        figures.card_sales,
        figures.other_sales,
    ) == (12100, 7100, 5000, 0)
    assert figures.expected_cash == 7100


def test_comps_go_apart_at_cost_once_per_sale(shirt):
    session = open_session(0)
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "comps-only-0001",
            "lines": [{"product": "SHIRT", "is_gift": True, "gift_reason": "birthday"}],
        },
    )
    (line,) = lines(session)
    # All comps: a line of zero with its cost; nothing in the drawer.
    assert (line.type, line.amount, line.gift_total) == ("sale", 0, 4000)
    assert (summary(session).total_gifts, summary(session).expected_cash) == (4000, 0)


def test_the_shift_follows_the_business_day_of_sale(coffee):
    session = open_session()
    assert session.business_day.isoformat() == str(run("sale.business_day.get").today)
    sale = charge()
    assert Sale.objects.get(pk=sale.id).business_day == session.business_day


# ── F14: voids ─────────────────────────────────────────────────────────────────────────────────


def test_a_sale_voided_in_the_same_shift_does_not_count(coffee):
    session = open_session(10000)
    sale = charge("2")
    void(sale)
    assert [(line.type, line.signed_amount) for line in lines(session)] == [
        ("sale", 300),
        ("void", -300),
    ]
    figures = summary(session)
    assert (figures.expected_cash, figures.total_sales, figures.total_refunds) == (
        10000,
        300,
        300,
    )


def test_a_card_sale_voided_moves_no_cash(coffee):
    session = open_session(10000)
    void(charge("1", payments=[{"method": "card"}]))
    assert [(line.type, line.method_type) for line in lines(session)] == [
        ("sale", "card"),
        ("void", "card"),
    ]
    assert summary(session).expected_cash == 10000


def test_a_sale_refunded_in_part_cannot_be_voided_so_the_drawer_never_pays_twice(coffee):
    # cash_register#63: voiding a sale already refunded in part reverted the WHOLE sale, so the drawer was
    # short by what had been refunded. Sales refuses that void: the refund is the only way back.
    session = open_session(10000)
    sale = charge("2")
    refund(sale, 100)
    with pytest.raises(Conflict) as refused:
        void(sale)
    assert refused.value.code == "sale.sale_already_refunded"
    assert [(line.type, line.amount) for line in lines(session)] == [
        ("sale", 300),
        ("refund", 100),
    ]
    assert summary(session).expected_cash == 10200


def test_a_card_sale_voided_with_the_drawer_closed_is_out_of_every_shift_and_moves_no_cash(
    coffee,
):
    # cash_register#82: a card void with no shift open, end to end against the real Sales: it is not lost,
    # it is said as unassigned, and it takes no cash out of any drawer.
    open_session(10000)
    sale = charge("1", payments=[{"method": "card"}])
    close(10000)
    void(sale)
    current = run("cash_register.session.current")
    assert (current.session, current.unassigned_count, current.unassigned_cash) == (
        None,
        1,
        0,
    )
    (line,) = run("cash_register.movement.list", {"unassigned": True}).rows
    assert (line.type, line.method_type, line.amount, line.sale_id) == (
        "void",
        "card",
        150,
        sale.id,
    )
    second = open_session(5000)
    assert summary(second).expected_cash == 5000


def test_a_sale_voided_after_its_shift_closed_takes_the_cash_out_of_the_open_shift(
    coffee,
):
    first = open_session(10000)
    sale = charge("2")
    close(10300)
    frozen = summary(first).model_dump()
    second = open_session(10300)
    void(sale)
    # The closed shift does not move: same figures, same lines, same frozen expected.
    assert summary(first).model_dump() == frozen
    assert [line.type for line in lines(first)] == ["sale"]
    assert Session.objects.get(pk=first.id).expected_balance == 10300
    # The cash leaves the drawer that is open now.
    assert [(line.type, line.amount, line.sale_number) for line in lines(second)] == [
        ("void", 300, sale.number)
    ]
    assert summary(second).expected_cash == 10000


# ── F15: refunds ───────────────────────────────────────────────────────────────────────────────


def test_a_card_sale_refunded_in_cash_takes_cash_out_of_the_drawer(shirt):
    # The product's own case (cash_register#62): float 100.00, a 121.00 sale by card, 50.00 back in cash.
    session = open_session(10000)
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "refund-to-cash-01",
            "lines": [{"product": "SHIRT"}],
            "payments": [{"method": "card"}],
        },
    )
    refund(sale, 5000, to_method_id=cash_method().id)
    refund_line = lines(session)[-1]
    assert (
        refund_line.type,
        refund_line.method_type,
        refund_line.signed_amount,
        refund_line.sale_number,
    ) == (
        "refund",
        "cash",
        -5000,
        sale.number,
    )
    assert summary(session).expected_cash == 5000
    assert summary(session).total_refunds == 5000


def test_a_cash_sale_refunded_to_a_card_does_not_touch_the_drawer(coffee):
    session = open_session(10000)
    sale = charge("2")
    refund(sale, 150, to_method_id=card_method().id)
    assert summary(session).expected_cash == 10300


def test_a_refund_of_a_sale_of_another_day_goes_to_the_open_shift(coffee):
    open_session(10000)
    sale = charge("2")
    close(10300)
    second = open_session(10300)
    refund(sale, 300)
    assert [(line.type, line.signed_amount) for line in lines(second)] == [
        ("refund", -300)
    ]
    assert summary(second).expected_cash == 10000


# ── F09: the close copies the shift and the count says the difference ──────────────────────────


def test_the_count_and_the_close_with_a_difference(coffee):
    session = open_session(10000)
    charge("1", payments=[{"method": "cash", "tendered": 500}])
    charge("1", payments=[{"method": "card"}])
    run(
        "cash_register.movement.add",
        {"type": "out", "amount": 1000, "description": "Bread"},
    )
    # 100.00 + 1.50 cash − 10.00 out = 91.50 expected; the drawer holds 91.00: 50 cents short.
    count = run(
        "cash_register.count.add",
        {"denominations": {"bills": {"50": 1, "20": 2}, "coins": {"1": 1}}},
    )
    assert count.total == 9100
    closed = close(count.total)
    assert (closed.expected_balance, closed.closing_balance, closed.difference) == (
        9150,
        9100,
        -50,
    )
    figures = summary(session)
    assert (
        figures.cash_sales,
        figures.card_sales,
        figures.total_cash_out,
        figures.difference,
    ) == (150, 150, 1000, -50)


def test_closing_copies_the_sale_lines_of_the_shift_once(coffee):
    session = open_session(10000)
    sale = charge("2")
    keys_open = [line.key for line in lines(session)]
    close(10300)
    copies = Movement.objects.filter(session_id=session.id, type="sale")
    assert copies.count() == 1
    copy = copies.get()
    assert (copy.sale_id, copy.sale_payment_id, copy.amount, copy.sale_number) == (
        sale.id,
        sale.payments[0].id,
        300,
        sale.number,
    )
    # The closed shift lists its copies with the same keys it had while open.
    assert [line.key for line in lines(session)] == keys_open


def test_an_auto_close_keeps_the_lines_before_the_cut_off_and_leaves_the_rest_unassigned(
    coffee,
):
    session = open_session(10000)
    early, late = charge("1"), charge("2")
    now = timezone.now()
    Session.objects.filter(pk=session.id).update(opened_at=now - dt.timedelta(days=2))
    run(
        "cash_register.settings.update",
        {"auto_close_enabled": True, "auto_close_time": "04:00"},
    )
    from apps.cash_register.queries import last_cut_off

    cut = last_cut_off(now, dt.time(4, 0))
    Sale.objects.filter(pk=early.id).update(created_at=cut - dt.timedelta(hours=1))
    Sale.objects.filter(pk=late.id).update(created_at=cut + dt.timedelta(minutes=1))
    (closed,) = run("cash_register.session.auto_close").closed
    assert closed.expected_balance == 10150
    assert [line.sale_id for line in lines(session)] == [early.id]
    # The late sale fell in no shift: it is said, not lost.
    current = run("cash_register.session.current")
    assert (current.unassigned_count, current.unassigned_cash) == (1, 300)


# ── F17: charged with the drawer closed ────────────────────────────────────────────────────────


def test_a_sale_charged_with_the_drawer_closed_is_shown_and_never_lands_in_the_next_shift(
    coffee,
):
    open_session(10000)
    close(10000)
    # Sales only charges cash with the drawer closed while «Activar caja» is off (F04).
    with drawer_lock_off():
        orphan = charge("2")
    charge("1", payments=[{"method": "card"}])
    current = run("cash_register.session.current")
    assert (current.session, current.unassigned_count, current.unassigned_cash) == (
        None,
        2,
        300,
    )
    unassigned = run("cash_register.movement.list", {"unassigned": True}).rows
    assert {
        (line.sale_id, line.session_id)
        for line in unassigned
        if line.method_type == "cash"
    } == {(orphan.id, None)}
    # The next shift starts from its own float: the orphan cash is counted in it, never added again.
    second = open_session(10300)
    assert lines(second) == []
    assert summary(second).expected_cash == 10300
    assert run("cash_register.session.current").unassigned_count == 0


def test_before_the_first_shift_there_is_nothing_unassigned(coffee):
    with drawer_lock_off():
        charge("1")
    current = run("cash_register.session.current")
    assert (current.unassigned_count, current.unassigned_cash) == (0, 0)


# ── Review 2026-10-14: what falls between shifts is never lost ─────────────────────────────────


def _due(session, days: int = 2) -> None:
    Session.objects.filter(pk=session.id).update(opened_at=timezone.now() - dt.timedelta(days=days))
    run("cash_register.settings.update", {"auto_close_enabled": True, "auto_close_time": "04:00"})


def test_sales_after_the_cut_of_a_forgotten_shift_are_said_before_opening_the_next(coffee):
    # A open since Monday, cut at 04:00, sales on Tuesday morning: they belong to no shift.
    forgotten = open_session(10000)
    _due(forgotten)
    charge("1")
    current = run("cash_register.session.current")
    assert current.session.auto_close_due is True
    assert (current.unassigned_count, current.unassigned_cash) == (1, 150)
    # The forgotten shift's own figures stop at its cut: what its auto-close will freeze.
    assert summary(forgotten).expected_cash == 10000
    assert [line.type for line in lines(forgotten)] == []
    assert len(run("cash_register.movement.list", {"unassigned": True}).rows) == 1
    # Opening the next one closes the forgotten one at the cut; the morning sale is in neither.
    second = open_session(10150)
    assert Session.objects.get(pk=forgotten.id).expected_balance == 10000
    assert lines(second) == []


def test_a_sale_confirmed_while_the_shift_was_closing_is_shown_as_a_straggler(coffee):
    first = open_session(10000)
    Session.objects.filter(pk=first.id).update(opened_at=timezone.now() - dt.timedelta(hours=8))
    close(10000)
    closed_at = Session.objects.get(pk=first.id).closed_at
    # Charged while the close was taking place: its moment is before the close, its commit after it.
    with drawer_lock_off():
        late = charge("1")
    Sale.objects.filter(pk=late.id).update(created_at=closed_at - dt.timedelta(seconds=1))
    open_session(10150)
    current = run("cash_register.session.current")
    assert (current.unassigned_count, current.unassigned_cash) == (1, 150)
    assert [line.sale_id for line in run("cash_register.movement.list", {"unassigned": True}).rows] == [late.id]


def test_with_the_cash_register_off_nothing_is_counted_as_unassigned(coffee):
    open_session(10000)
    close(10000)
    run("cash_register.settings.update", {"enable_cash_register": False})
    charge("1")
    current = run("cash_register.session.current")
    assert (current.required, current.unassigned_count, current.unassigned_cash) == (False, 0, 0)


def test_the_unassigned_counts_add_up_every_kind_of_line(coffee, shirt):
    open_session(10000)
    close(10000)
    with drawer_lock_off():
        cash = charge("2")
        card = charge("1", payments=[{"method": "card"}])
        void(card)
        refund(cash, 100)
        run(
            "sale.sale.complete",
            {"idempotency_key": "unassigned-comps-01", "lines": [{"product": "SHIRT", "is_gift": True}]},
        )
    listed = run("cash_register.movement.list", {"unassigned": True}).rows
    current = run("cash_register.session.current")
    assert current.unassigned_count == len(listed) == 5
    # 3.00 in cash charged, 1.00 of it refunded in cash; the card sale and its void move no cash.
    assert current.unassigned_cash == sum(line.signed_amount for line in listed if line.method_type == "cash") == 200


# ── F04: Sales asks the drawer before charging cash (its contract, applied by sale) ─────────────


def test_sales_refuses_cash_with_the_drawer_on_and_closed_and_charges_the_rest(coffee):
    # «Activar caja» on (the factory value) and no session open: cash is refused, a card is not.
    with pytest.raises(Conflict) as refused:
        charge("1")
    assert refused.value.code == "sale.cash_register_closed"
    assert not Sale.objects.exists()
    charge("1", payments=[{"method": "card"}])
    # With the drawer open, cash is charged; and in the shift.
    session = open_session(10000)
    charge("1")
    assert summary(session).expected_cash == 10150


def test_sales_charges_cash_in_a_forgotten_shift_past_its_cut(coffee):
    # The forgotten session is still open: Sales charges, and the line is out of every shift (F10, F17).
    forgotten = open_session(10000)
    _due(forgotten)
    charge("1")
    assert run("cash_register.session.current").unassigned_cash == 150


def test_with_the_drawer_off_sales_charges_cash_with_no_session(coffee):
    run("cash_register.settings.update", {"enable_cash_register": False})
    assert charge("1").total == 150


def test_when_the_drawer_does_not_answer_sales_charges_and_the_line_is_out_of_every_shift(coffee, monkeypatch):
    # «Caja no responde»: Sales finds no `cash_register.session.current` and charges anyway (F04 cede);
    # once the drawer answers again, that cash is said as out of every shift (F17).
    from live import operations

    open_session(10000)
    close(10000)
    current = operations.registry["cash_register.session.current"]
    monkeypatch.delitem(operations.registry, "cash_register.session.current")
    lost = charge("2")
    monkeypatch.setitem(operations.registry, "cash_register.session.current", current)
    seen = run("cash_register.session.current")
    assert (seen.unassigned_count, seen.unassigned_cash) == (1, 300)
    assert [line.sale_id for line in run("cash_register.movement.list", {"unassigned": True}).rows] == [lost.id]

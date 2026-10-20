"""The reads of the sale app (SALE-F06, F17, F21, F22, F28, F29, F31, F34–F36), each ``READ ONLY``."""

import datetime as dt
from decimal import Decimal
from uuid import uuid7

import pytest
from django.utils import timezone, translation
from live.errors import NotFound, PermissionDenied

from apps.sale.models import PaymentMethod, Sale
from apps.sale.tests.conftest import ctx_for, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture
def catalog(product):
    product("Coffee", "COF", 121, "product.generic")
    product("Water", "WAT", 110, "restaurant.drink")
    product("Steak", "STK", 1800, "restaurant.food")


def charge(key: str, lines=({"product": "COF"},), **more):
    return run(
        "sale.sale.complete", {"idempotency_key": key, "lines": list(lines), **more}
    )


def set_day(sale, day: dt.date, at: dt.datetime | None = None) -> None:
    """Moves a sale to another business day (what a sale charged that day would have)."""
    Sale.objects.filter(pk=sale.id).update(
        business_day=day, created_at=at or dt.datetime.combine(day, dt.time(12), dt.UTC)
    )


# ── The sales list ──────────────────────────────────────────────────────────────────────────────


def test_the_list_newest_first_with_search_by_number_or_customer(catalog, customer):
    ana = customer("Ana López")
    first = charge("list-key-0001", customer_id=str(ana.id))
    second = charge(
        "list-key-0002", lines=[{"product": "STK"}], payments=[{"method": "card"}]
    )
    page = run("sale.sale.list", {})
    assert [row.id for row in page.rows] == [second.id, first.id] and page.total == 2
    row = page.rows[1]
    assert (
        row.number,
        row.customer_name,
        row.payment_method_name,
        row.total,
        row.status,
    ) == (first.number, "Ana López", "Cash", 121, "completed")
    assert [r.id for r in run("sale.sale.list", {"search": "lópez"}).rows] == [first.id]
    assert [
        r.id for r in run("sale.sale.list", {"search": second.number[-4:]}).rows
    ] == [second.id]
    # The method is filtered, never searched: the screen shows it translated.
    assert run("sale.sale.list", {"search": "Cash"}).rows == []
    assert [
        r.id for r in run("sale.sale.list", {"payment_method_name": "Card"}).rows
    ] == [second.id]


def test_the_list_filters_by_status_days_total_and_staff(catalog):
    staff = uuid7()
    old = charge("list-key-0001")
    big = charge("list-key-0002", lines=[{"product": "STK"}], staff_id=str(staff))
    voided = charge("list-key-0003")
    run("sale.sale.void", {"sale_id": str(voided.id), "reason": "x"})
    set_day(old, dt.date(2026, 9, 1))
    assert [r.id for r in run("sale.sale.list", {"status": "voided"}).rows] == [
        voided.id
    ]
    assert [
        r.id
        for r in run(
            "sale.sale.list", {"date_from": "2026-09-01", "date_to": "2026-09-01"}
        ).rows
    ] == [old.id]
    assert {
        r.id
        for r in run("sale.sale.list", {"date_from": str(timezone.localdate())}).rows
    } == {big.id, voided.id}
    assert [r.id for r in run("sale.sale.list", {"total_min": 1000}).rows] == [big.id]
    assert [r.id for r in run("sale.sale.list", {"staff_id": str(staff)}).rows] == [
        big.id
    ]


def test_the_list_sorts_numbers_as_numbers_and_pages(catalog):
    sales = [charge(f"list-key-{i:04}") for i in range(3)]
    Sale.objects.filter(pk=sales[0].id).update(number="20260901-10000", sequence=10000)
    Sale.objects.filter(pk=sales[1].id).update(number="20260901-2000", sequence=2000)
    Sale.objects.filter(pk=sales[2].id).update(number="20260901-0999", sequence=999)
    Sale.objects.update(business_day=dt.date(2026, 9, 1))
    rows = run("sale.sale.list", {"sort": "number", "dir": "asc"}).rows
    assert [row.number for row in rows] == [
        "20260901-0999",
        "20260901-2000",
        "20260901-10000",
    ]
    page = run(
        "sale.sale.list", {"sort": "number", "dir": "asc", "limit": 1, "offset": 1}
    )
    assert ([row.number for row in page.rows], page.total) == (["20260901-2000"], 3)


def test_a_partly_refunded_sale_says_what_is_left(catalog):
    sale = charge(
        "list-key-0001", lines=[{"product": "STK"}], payments=[{"method": "card"}]
    )
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "x",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 300}],
        },
    )
    (row,) = run("sale.sale.list", {}).rows
    assert (row.status, row.refunded_total, row.refundable_total) == (
        "completed",
        300,
        1500,
    )


def test_a_row_says_whether_the_sale_has_refunds_also_one_of_no_money(catalog):
    # A refund that gave back only a voucher's session moves no money: the row still says the sale has
    # refunds, so the screen offers «Refund» and never «Void» (the server refuses voiding it).
    from apps.sale.models import Refund

    plain = charge("list-key-0002", payments=[{"method": "card"}])
    session_only = charge("list-key-0003", payments=[{"method": "card"}])
    Refund.objects.create(sale_id=session_only.id, total=0, reason="the session")
    rows = {row.id: row for row in run("sale.sale.list", {}).rows}
    assert (rows[plain.id].has_refunds, rows[session_only.id].has_refunds) == (False, True)
    assert rows[session_only.id].refunded_total == 0


def test_an_employee_reads_the_sales_but_not_the_figures(catalog):
    charge("list-key-0001")
    employee = ctx_for(EMPLOYEE)
    assert run("sale.sale.list", {}, employee).total == 1
    with pytest.raises(PermissionDenied):
        run("sale.sale.stats", {}, employee)


# ── One sale ────────────────────────────────────────────────────────────────────────────────────


def test_a_sale_by_its_id_or_its_number(catalog):
    sale = charge(
        "get-key-0001",
        lines=[{"product": "COF", "quantity": "2"}],
        payments=[{"method": "cash", "tendered": 500}],
    )
    found = run("sale.sale.get", {"sale": sale.number})
    assert found.id == sale.id and found.change_total == 258 and len(found.lines) == 1
    assert found.lines[0].returned_quantity == Decimal("0")
    with pytest.raises(NotFound):
        run("sale.sale.get", {"sale_id": str(uuid7())})


def test_the_factory_methods_read_in_the_readers_language(catalog):
    sale = charge("get-key-0001")
    with translation.override("es"):
        found = run("sale.sale.get", {"sale_id": str(sale.id)}, ctx_for(language="es"))
    assert (
        found.payments[0].method_name == "Efectivo"
        and found.payment_method_name == "Efectivo"
    )


def test_a_sale_by_its_attempt_key(catalog):
    sale = charge("key-lookup-01")
    assert (
        run(
            "sale.sale.by_idempotency_key", {"idempotency_key": "key-lookup-01"}
        ).sale.id
        == sale.id
    )
    assert (
        run("sale.sale.by_idempotency_key", {"idempotency_key": "key-lookup-02"}).found
        is False
    )


# ── Figures ─────────────────────────────────────────────────────────────────────────────────────


def test_the_figures_of_a_period(catalog):
    today = timezone.localdate()
    one = charge(
        "stats-key-0001", lines=[{"product": "STK"}], payments=[{"method": "card"}]
    )  # 1800
    two = charge(
        "stats-key-0002",
        lines=[{"product": "STK"}],
        discount_percent="50",
        payments=[{"method": "card"}],
    )
    voided = charge("stats-key-0003")
    run("sale.sale.void", {"sale_id": str(voided.id), "reason": "x"})
    run(
        "sale.sale.refund",
        {
            "sale_id": str(one.id),
            "reason": "x",
            "allocations": [{"payment_id": str(one.payments[0].id), "amount": 300}],
        },
    )
    old = charge("stats-key-0004")
    set_day(old, today - dt.timedelta(days=40))
    stats = run("sale.sale.stats", {"date_from": str(today), "date_to": str(today)})
    assert (stats.count, stats.voided_count) == (2, 1)
    assert stats.total_revenue == 1800 + 900 - 300
    assert stats.refunded_total == 300 and stats.discount_total == 900
    assert stats.avg_ticket == (1800 + 900 - 300) // 2
    assert (
        stats.net_total == one.subtotal + two.subtotal
        and stats.tax_total == one.tax_total + two.tax_total
    )
    assert run("sale.sale.stats", {}).count == 3


def test_a_sale_refunded_in_full_still_counts_as_a_ticket_with_no_revenue(catalog):
    sale = charge(
        "stats-key-0001", lines=[{"product": "STK"}], payments=[{"method": "card"}]
    )
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "x",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 1800}],
        },
    )
    stats = run("sale.sale.stats", {})
    assert (stats.count, stats.total_revenue) == (1, 0)


def test_today_and_the_last_seven_days(catalog):
    today = timezone.localdate()
    charge("days-key-0001")
    two_days_ago = charge(
        "days-key-0002", lines=[{"product": "STK"}], payments=[{"method": "card"}]
    )
    set_day(two_days_ago, today - dt.timedelta(days=2))
    eight_days_ago = charge("days-key-0003")
    set_day(eight_days_ago, today - dt.timedelta(days=8))
    voided = charge("days-key-0004")
    run("sale.sale.void", {"sale_id": str(voided.id), "reason": "x"})
    assert run("sale.sale.today", {}).model_dump() == {
        "day": today,
        "total": 121,
        "tickets": 1,
    }
    rows = run("sale.sale.last_7_days", {}).rows
    assert [row.day for row in rows] == [
        today - dt.timedelta(days=d) for d in range(6, -1, -1)
    ]
    assert [row.total for row in rows] == [0, 0, 0, 0, 1800, 0, 121]


def test_by_professional_the_lines_staff_wins_over_the_sales(catalog):
    ana, luis = uuid7(), uuid7()
    charge(
        "staff-key-0001",
        lines=[{"product": "STK", "staff_id": str(luis)}, {"product": "COF"}],
        staff_id=str(ana),
        payments=[{"method": "card"}],
    )
    charge("staff-key-0002", lines=[{"product": "COF"}], staff_id=str(ana))
    charge("staff-key-0003", lines=[{"product": "COF"}])
    rows = run("sale.sale.by_staff", {}).rows
    assert [(row.staff_id, row.sales_count, row.gross_total) for row in rows] == [
        (luis, 1, 1800),
        (ana, 2, 242),
    ]
    assert all(row.net_total + row.tax_total == row.gross_total for row in rows)


def give_back(sale, amount: int, *lines: dict):
    """A refund of ``amount`` cents on the sale's first tender, returning ``lines`` (SALE-F31)."""
    return run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "returned",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": amount}],
            "lines": list(lines),
        },
    )


def test_by_professional_a_refund_comes_off_who_sold_what_came_back(catalog):
    # flow: ninguno — FIX sale/cash_register (de STAFF-F21 y REC_PELUQUERIA-F15): what each one sold
    # squares with the period's revenue to the cent, refunds taken off, so a commission is never paid
    # on money that went back.
    ana, luis, bea = uuid7(), uuid7(), uuid7()
    card = [{"method": "card"}]
    # 1 of Luis's 2 steaks comes back for 10.00: all of it comes off Luis, nothing off Ana.
    first = charge(
        "refund-staff-0001",
        lines=[{"product": "STK", "quantity": "2", "staff_id": str(luis)}, {"product": "COF"}],
        staff_id=str(ana),
        payments=card,
    )
    steaks = next(line for line in first.lines if line.sku == "STK")
    give_back(first, 1000, {"line_id": str(steaks.id), "quantity": "1"})
    # Money only, all of it: Bea's sale is refunded whole.
    second = charge(
        "refund-staff-0002", lines=[{"product": "STK"}], staff_id=str(bea), payments=card
    )
    give_back(second, 1800)
    # Money only, a part: shared by what each one's lines charged (1.21 and 1.10 → 0.52 and 0.48).
    third = charge(
        "refund-staff-0003",
        lines=[{"product": "COF"}, {"product": "WAT", "staff_id": str(luis)}],
        staff_id=str(ana),
        payments=card,
    )
    give_back(third, 100)
    charge("refund-staff-0004", staff_id=str(ana))
    rows = run("sale.sale.by_staff", {}).rows
    assert [
        (row.staff_id, row.sales_count, row.gross_total, row.refunded_total, row.total_revenue)
        for row in rows
    ] == [
        (luis, 2, 3710, 1048, 2662),
        (ana, 3, 363, 52, 311),
        (bea, 1, 1800, 1800, 0),
    ]
    assert sum(row.total_revenue for row in rows) == run("sale.sale.stats", {}).total_revenue == 2973


def test_by_professional_money_back_on_a_line_worth_nothing_is_shared_by_what_charged(catalog):
    ana, luis = uuid7(), uuid7()
    sale = charge(
        "refund-staff-0005",
        lines=[{"product": "COF", "is_gift": True}, {"product": "STK", "staff_id": str(luis)}],
        staff_id=str(ana),
        payments=[{"method": "card"}],
    )
    comp = next(line for line in sale.lines if line.is_gift)
    # The comp comes back with 10.00: it charged nothing, so the money comes off what did charge.
    give_back(sale, 1000, {"line_id": str(comp.id)})
    rows = run("sale.sale.by_staff", {}).rows
    assert [(row.staff_id, row.gross_total, row.refunded_total, row.total_revenue) for row in rows] == [
        (luis, 1800, 1000, 800),
        (ana, 0, 0, 0),
    ]


def test_by_professional_several_lines_back_share_the_money_by_what_came_back(catalog):
    ana, luis = uuid7(), uuid7()
    sale = charge(
        "refund-staff-0007",
        lines=[
            {"product": "STK", "quantity": "2", "staff_id": str(luis)},
            {"product": "COF", "quantity": "3"},
        ],
        staff_id=str(ana),
        payments=[{"method": "card"}],
    )
    steaks, coffees = sorted(sale.lines, key=lambda line: line.sku != "STK")
    # 1 steak of 2 (18.00) and the 3 coffees (3.63) come back for 10.00: 8.32 and 1.68.
    give_back(
        sale,
        1000,
        {"line_id": str(steaks.id), "quantity": "1"},
        {"line_id": str(coffees.id)},
    )
    rows = run("sale.sale.by_staff", {}).rows
    assert [(row.staff_id, row.refunded_total, row.total_revenue) for row in rows] == [
        (luis, 832, 2768),
        (ana, 168, 195),
    ]


def test_by_professional_a_refund_belongs_to_the_day_of_its_sale(catalog):
    ana = uuid7()
    today = timezone.localdate()
    yesterday = today - dt.timedelta(days=1)
    sale = charge(
        "refund-staff-0006", lines=[{"product": "STK"}], staff_id=str(ana), payments=[{"method": "card"}]
    )
    give_back(sale, 500)
    set_day(sale, yesterday)
    charge("refund-staff-0008", staff_id=str(ana))
    [row] = run("sale.sale.by_staff", {"date_from": today}).rows
    assert (row.gross_total, row.refunded_total, row.total_revenue) == (121, 0, 121)
    [row] = run("sale.sale.by_staff", {"date_to": yesterday}).rows
    assert (row.gross_total, row.refunded_total, row.total_revenue) == (1800, 500, 1300)


def test_the_business_day():
    assert run("sale.business_day.get", {}).today == timezone.localdate()


# ── The preview of a charge ─────────────────────────────────────────────────────────────────────


def test_the_preview_values_a_check_without_writing_anything(catalog):
    order = run(
        "sale.order.open",
        {"lines": [{"product": "COF", "quantity": "2"}, {"product": "WAT"}]},
    )
    preview = run("sale.checkout.preview", {"order_id": str(order.id)})
    assert (
        preview.total,
        preview.subtotal,
        preview.tax_total,
        preview.lines_count,
    ) == (352, 300, 52, 2)
    assert (preview.order_version, preview.cash_limit, preview.ticket_limit) == (
        order.version,
        100000,
        300000,
    )
    assert [line.line_total for line in preview.lines] == [242, 110]
    assert Sale.objects.count() == 0


def test_the_preview_of_some_lines_or_of_loose_ones(catalog):
    order = run("sale.order.open", {"lines": [{"product": "COF"}, {"product": "STK"}]})
    part = run(
        "sale.checkout.preview",
        {"order_id": str(order.id), "line_ids": [str(order.lines[1].id)]},
    )
    assert (part.total, part.lines_count) == (1800, 1)
    loose = run(
        "sale.checkout.preview",
        {"lines": [{"product": "STK"}], "discount_percent": "10"},
    )
    assert (loose.total, loose.discount_amount, loose.order_id) == (1620, 180, None)


# ── Open checks ─────────────────────────────────────────────────────────────────────────────────


def test_the_open_checks_newest_first(catalog):
    first = run(
        "sale.order.open", {"label": "Ana — terrace", "lines": [{"product": "COF"}]}
    )
    second = run("sale.order.open", {"label": "Table 4"})
    closed = run("sale.order.open", {"lines": [{"product": "COF"}]})
    run("sale.order.void", {"order_id": str(closed.id)})
    page = run("sale.order.list", {})
    assert [row.id for row in page.rows] == [second.id, first.id]
    assert (
        page.rows[1].label,
        page.rows[1].provisional_total,
        page.rows[1].lines_count,
    ) == ("Ana — terrace", 121, 1)
    assert [row.id for row in run("sale.order.list", {"search": "terr"}).rows] == [
        first.id
    ]
    assert [row.id for row in run("sale.order.list", {"status": "voided"}).rows] == [
        closed.id
    ]


def test_a_check_shows_only_the_lines_left_to_charge(catalog):
    order = run("sale.order.open", {"lines": [{"product": "COF"}, {"product": "STK"}]})
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "order-key-01",
            "order_id": str(order.id),
            "line_ids": [str(order.lines[0].id)],
        },
    )
    left = run("sale.order.get", {"order_id": str(order.id)})
    assert (
        [line.name for line in left.lines] == ["Steak"]
        and left.lines_count == 1
        and left.provisional_total == 1800
    )
    with pytest.raises(NotFound):
        run("sale.order.get", {"order_id": str(uuid7())})


# ── Catalogues and settings ─────────────────────────────────────────────────────────────────────


def test_the_payment_methods_say_which_ones_the_settings_allow():
    run("sale.payment_method.create", {"name": "Bizum", "type": "other"})
    run("sale.payment_method.create", {"name": "Transfer", "type": "transfer"})
    rows = run("sale.payment_method.list", {}).rows
    assert [(row.name, row.type, row.allowed) for row in rows] == [
        ("Cash", "cash", True),
        ("Card", "card", True),
        ("Bizum", "other", True),
        ("Transfer", "transfer", False),
    ]
    with translation.override("es"):
        names = [
            row.display_name
            for row in run("sale.payment_method.list", {}, ctx_for(language="es")).rows
        ]
    assert names[:2] == ["Efectivo", "Tarjeta"]
    PaymentMethod.objects.filter(name="Bizum").update(is_active=False)
    assert "Bizum" not in [row.name for row in run("sale.payment_method.list", {}).rows]


def test_the_settings_read_the_factory_values_until_saved():
    settings = run("sale.settings.get", {})
    assert (
        settings.updated_at,
        settings.allow_cash,
        settings.max_discount_percent,
        settings.default_document_type,
    ) == (None, True, 100, "ticket")
    run("sale.settings.update", {"max_discount_percent": 20})
    assert run("sale.settings.get", {}).max_discount_percent == 20
    with pytest.raises(PermissionDenied):
        run("sale.settings.get", {}, ctx_for(EMPLOYEE))
    # The till reads them with the permission to sell.
    assert (
        run("sale.pos_settings.get", {}, ctx_for(EMPLOYEE)).max_discount_percent == 20
    )


def test_departments_in_their_order_with_their_rate_today():
    run(
        "sale.department.create",
        {"name": "Meat", "tax_category_key": "product.reduced", "sort_order": 20},
    )
    run(
        "sale.department.create",
        {
            "name": "Fruit",
            "tax_category_key": "product.super_reduced",
            "sort_order": 10,
        },
    )
    deleted = run(
        "sale.department.create", {"name": "Old", "tax_category_key": "product.generic"}
    )
    run("sale.department.delete", {"id": str(deleted.id)})
    rows = run("sale.department.list", {}, ctx_for(EMPLOYEE)).rows
    assert [(row.name, row.tax_rate_pct) for row in rows] == [
        ("Fruit", Decimal("4.00")),
        ("Meat", Decimal("10.00")),
    ]
    assert [
        row.name for row in run("sale.department.list", {"search": "mea"}).rows
    ] == ["Meat"]
    assert [
        row.name
        for row in run("sale.department.list", {"sort": "name", "dir": "desc"}).rows
    ] == ["Meat", "Fruit"]


def test_quick_notes_in_their_order():
    run("sale.quick_note.create", {"text": "no salt", "sort_order": 20})
    run("sale.quick_note.create", {"text": "medium rare", "sort_order": 10})
    assert [
        row.text for row in run("sale.quick_note.list", {}, ctx_for(EMPLOYEE)).rows
    ] == ["medium rare", "no salt"]
    assert [
        row.text for row in run("sale.quick_note.list", {"search": "salt"}).rows
    ] == ["no salt"]


# ── Refunds ─────────────────────────────────────────────────────────────────────────────────────


def test_what_a_sale_can_still_give_back(catalog):
    sale = charge(
        "refund-key-01",
        lines=[{"product": "STK"}, {"product": "COF", "quantity": "3"}],
        payments=[
            {"method": "card", "amount": 2000},
            {"method": "cash", "amount": 163},
        ],
    )
    card, cash = sale.payments
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "x",
            "idempotency_key": "refund-key-01",
            "allocations": [{"payment_id": str(cash.id), "amount": 163}],
            "lines": [{"line_id": str(sale.lines[1].id), "quantity": "1"}],
        },
    )
    options = run("sale.refund.options", {"sale_id": str(sale.id)})
    assert [
        (t.charged, t.refunded, t.remaining, t.refundable, t.reason)
        for t in options.tenders
    ] == [
        (2000, 0, 2000, True, ""),
        (163, 163, 0, False, "already_refunded"),
    ]
    assert [
        (line.name, line.quantity, line.returned, line.left) for line in options.lines
    ] == [
        ("Steak", Decimal("1.000"), Decimal("0"), Decimal("1.000")),
        ("Coffee", Decimal("3.000"), Decimal("1.000"), Decimal("2.000")),
    ]
    (row,) = run("sale.refund.list", {"sale_id": str(sale.id)}).rows
    assert (row.total, row.reason) == (163, "x")
    assert (
        run(
            "sale.refund.by_idempotency_key", {"idempotency_key": "refund-key-01"}
        ).refund.id
        == row.id
    )
    assert (
        run(
            "sale.refund.by_idempotency_key", {"idempotency_key": "refund-key-02"}
        ).found
        is False
    )

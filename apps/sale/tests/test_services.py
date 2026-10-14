"""The till's catalogues and settings (SALE-F33–F37): payment methods, settings, departments, quick
notes, and the reaction to two customer cards merged. Opening and charging checks, voids and refunds
have their own files (test_services_order.py, test_services_checkout.py, test_services_refund.py).
"""

from decimal import Decimal
from uuid import uuid7

import pytest
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.sale.models import Department, PaymentMethod, QuickNote, Sale, Settings
from apps.sale.tests.conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


def events() -> list[tuple[str, dict]]:
    return [
        (e.name, e.payload)
        for e in OutboxEvent.objects.filter(name__startswith="sale.").order_by(
            "created_at", "id"
        )
    ]


# ── Settings ────────────────────────────────────────────────────────────────────────────────────


def test_saving_settings_changes_only_what_is_sent(make_user):
    saved = run(
        "sale.settings.update",
        {"require_customer": True, "max_discount_percent": 15},
        ctx_for(actor="boss"),
    )
    assert (saved.require_customer, saved.max_discount_percent, saved.allow_cash) == (
        True,
        15,
        True,
    )
    saved = run("sale.settings.update", {"receipt_header": "Bar Manolo\nC/ Mayor 1"})
    assert (saved.require_customer, saved.receipt_header) == (
        True,
        "Bar Manolo\nC/ Mayor 1",
    )
    assert (
        Settings.objects.count() == 1 and Settings.objects.get().updated_by == "tester"
    )
    assert [name for name, _ in events()] == [
        "sale.settings.updated",
        "sale.settings.updated",
    ]


def test_saving_the_same_settings_says_nothing():
    run("sale.settings.update", {"allow_transfer": True})
    OutboxEvent.objects.all().delete()
    run("sale.settings.update", {"allow_transfer": True})
    assert events() == []


def test_the_settings_are_the_managers():
    with pytest.raises(PermissionDenied):
        run("sale.settings.update", {"allow_cash": False}, ctx_for(EMPLOYEE))


# ── Payment methods ─────────────────────────────────────────────────────────────────────────────


def test_a_new_payment_method_is_cash_unless_its_type_is_said():
    bizum = run("sale.payment_method.create", {"name": "Bizum", "type": "other"})
    assert (bizum.name, bizum.display_name, bizum.type, bizum.requires_change) == (
        "Bizum",
        "Bizum",
        "other",
        False,
    )
    voucher = run("sale.payment_method.create", {"name": "Voucher"})
    assert voucher.type == "cash" and voucher.requires_change is True
    assert events()[0] == (
        "sale.payment_method.created",
        {"id": str(bizum.id), "type": "other"},
    )


def test_a_payment_method_name_is_not_repeated():
    with pytest.raises(Conflict) as refusal:
        run("sale.payment_method.create", {"name": "cash"})
    assert refusal.value.code == "sale.payment_method_exists"
    assert set(refusal.value.fields) == {"name"}


def test_creating_payment_methods_is_the_managers():
    with pytest.raises(PermissionDenied):
        run("sale.payment_method.create", {"name": "Bizum"}, ctx_for(EMPLOYEE))


# ── Departments ─────────────────────────────────────────────────────────────────────────────────


def test_a_department_charges_at_a_tax_category_named_by_key_name_or_alias():
    fruit = run(
        "sale.department.create",
        {
            "name": "Fruit",
            "tax_category_key": "product.super_reduced",
            "sort_order": 10,
        },
    )
    assert (
        fruit.name,
        fruit.tax_category_key,
        fruit.tax_rate_pct,
        fruit.sort_order,
    ) == ("Fruit", "product.super_reduced", Decimal("4.00"), 10)
    meat = run(
        "sale.department.create",
        {
            "name": "Meat",
            "tax_category_key": "Product — reduced (food staples, pharmacy)",
        },
    )
    assert meat.tax_category_key == "product.reduced"
    # Two departments may share one category.
    assert (
        run(
            "sale.department.create",
            {"name": "Veg", "tax_category_key": "product.super_reduced"},
        ).tax_category_key
        == "product.super_reduced"
    )
    assert events()[0] == ("sale.department.created", {"id": str(fruit.id)})


def test_a_department_with_an_unknown_category_is_refused_on_its_field():
    with pytest.raises(InvalidPayload) as refusal:
        run("sale.department.create", {"name": "Ghost", "tax_category_key": "nowhere"})
    assert set(refusal.value.fields) == {"tax_category_key"}


def test_changing_a_department(make_user):
    fruit = run(
        "sale.department.create",
        {"name": "Fruit", "tax_category_key": "product.super_reduced"},
    )
    changed = run(
        "sale.department.update",
        {
            "department": "fruit",
            "name": "Greengrocer",
            "sort_order": 5,
            "tax_category_key": "product.generic",
        },
    )
    assert (changed.id, changed.name, changed.sort_order, changed.tax_category_key) == (
        fruit.id,
        "Greengrocer",
        5,
        "product.generic",
    )
    # What is not sent is kept.
    assert (
        run("sale.department.update", {"id": str(fruit.id), "sort_order": 7}).name
        == "Greengrocer"
    )


def test_deleting_a_department_hides_it_and_keeps_its_row():
    fruit = run(
        "sale.department.create",
        {"name": "Fruit", "tax_category_key": "product.super_reduced"},
    )
    run("sale.department.delete", {"id": str(fruit.id)})
    row = Department.objects.get(pk=fruit.id)
    assert row.is_deleted and row.deleted_at is not None
    with pytest.raises(NotFound) as refusal:
        run("sale.department.delete", {"id": str(fruit.id)})
    assert refusal.value.code == "sale.department_not_found"
    with pytest.raises(NotFound):
        run("sale.department.update", {"id": str(fruit.id), "name": "x"})


def test_a_department_named_aloud_must_be_one():
    run(
        "sale.department.create",
        {"name": "Fruit", "tax_category_key": "product.super_reduced"},
    )
    run(
        "sale.department.create",
        {"name": "Fruit juice", "tax_category_key": "product.generic"},
    )
    assert (
        run("sale.department.update", {"department": "fruit", "sort_order": 1}).name
        == "Fruit"
    )
    with pytest.raises(Conflict) as refusal:
        run("sale.department.update", {"department": "fru", "sort_order": 1})
    assert refusal.value.code == "sale.department_ambiguous"


def test_departments_are_the_managers():
    with pytest.raises(PermissionDenied):
        run(
            "sale.department.create",
            {"name": "Fruit", "tax_category_key": "product.generic"},
            ctx_for(EMPLOYEE),
        )


# ── Quick notes ─────────────────────────────────────────────────────────────────────────────────


def test_quick_notes_are_created_changed_and_deleted():
    note = run("sale.quick_note.create", {"text": "no salt", "sort_order": 20})
    assert (note.text, note.sort_order) == ("no salt", 20)
    changed = run(
        "sale.quick_note.update",
        {"quick_note": "no salt", "text": "very rare", "sort_order": 5},
    )
    assert (changed.id, changed.text, changed.sort_order) == (note.id, "very rare", 5)
    run("sale.quick_note.delete", {"id": str(note.id)})
    assert QuickNote.objects.get(pk=note.id).is_deleted
    with pytest.raises(NotFound) as refusal:
        run("sale.quick_note.delete", {"id": str(note.id)})
    assert refusal.value.code == "sale.quick_note_not_found"
    assert [name for name, _ in events()] == [
        "sale.quick_note.created",
        "sale.quick_note.updated",
        "sale.quick_note.deleted",
    ]


def test_quick_notes_are_the_managers():
    with pytest.raises(PermissionDenied):
        run("sale.quick_note.create", {"text": "no salt"}, ctx_for(EMPLOYEE))


# ── Two customer cards merged (SALE-F33) ────────────────────────────────────────────────────────


def test_merging_two_cards_moves_their_sales_and_keeps_the_printed_name(
    product, customer
):
    product("Coffee", "COF", 150, "product.generic")
    ana = customer("Ana López")
    duplicate = customer("Ana Lopez")
    other = customer("Luis")
    for index, card in enumerate([duplicate, duplicate, other, ana]):
        run(
            "sale.sale.complete",
            {
                "idempotency_key": f"merge-key-{index:04}",
                "lines": [{"product": "COF"}],
                "customer_id": str(card.id),
            },
        )
    run(
        "sale.sale.void",
        {
            "sale_id": str(Sale.objects.filter(customer_id=duplicate.id).first().id),
            "reason": "x",
        },
    )
    OutboxEvent.objects.all().delete()
    moved = run(
        "sale.customer.reassign",
        {"id": str(ana.id), "absorbed_id": str(duplicate.id)},
        system_context(A),
    )
    assert (moved.customer_id, moved.moved) == (ana.id, 2)
    assert Sale.objects.filter(customer_id=ana.id).count() == 3
    assert sorted(
        Sale.objects.filter(customer_id=ana.id).values_list("customer_name", flat=True)
    ) == ["Ana Lopez", "Ana Lopez", "Ana López"]
    assert Sale.objects.filter(customer_id=other.id).count() == 1
    assert events() == [
        (
            "sale.sale.reassigned",
            {"customer_id": str(ana.id), "absorbed_id": str(duplicate.id)},
        )
    ]
    # A redelivery changes nothing and says nothing.
    OutboxEvent.objects.all().delete()
    assert (
        run(
            "sale.customer.reassign",
            {"id": str(ana.id), "absorbed_id": str(duplicate.id)},
            system_context(A),
        ).moved
        == 0
    )
    assert events() == []


def test_only_the_platform_reassigns_sales():
    with pytest.raises(PermissionDenied):
        run("sale.customer.reassign", {"id": str(uuid7()), "absorbed_id": str(uuid7())})


def test_the_factory_methods_are_in_place():
    assert sorted(PaymentMethod.objects.values_list("type", flat=True)) == [
        "card",
        "cash",
    ]

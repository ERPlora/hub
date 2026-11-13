"""The card of a write of Sales (hub#561) says which record it acts on by its name, read as whoever asks, never by its
id, and left out when that person may not read it. A value of a closed list goes by the word its screens give it, in
English and in Spanish.

Sales requires only Taxes and Customers: what Inventory, Services, Menus, Modifiers, Staff and Appointments name reaches
the card through ``sale.record.get``, which asks each of those apps by its own operation.
"""

import dataclasses
import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.assistant import NAMED
from live.context import Scope, system_context
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.operations import get
from pydantic import ValidationError

from apps.customer.tax_ids import ID_TYPES
from apps.sale.models import ForeignIdType, OrderLine, QuickNote
from apps.sale.tests.conftest import A, ctx_for, run
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

KEY = "card-attempt-0001"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for(language=language))
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def flat(value) -> str:
    """Money as the reader writes it, with its no-break space said as a space."""
    return value.replace("\xa0", " ")


@pytest.fixture
def shampoo(product):
    return product("Shampoo", "SHP", 1210, "product.generic")


@pytest.fixture
def order(shampoo):
    return run("sale.order.open", {"label": "Table 4", "lines": [{"product_id": str(shampoo.id)}]})


@pytest.fixture
def sale(shampoo):
    cash = run("sale.payment_method.list", {}).rows[0]
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": KEY,
            "lines": [{"product_id": str(shampoo.id)}],
            "payments": [{"method_id": str(cash.id)}],
        },
    )


# ── Sales' own records ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Section"), ("es", "Sección")])
def test_a_section_is_said_by_its_name_and_titled_as_its_screen(language, title):
    section = run("sale.department.create", {"name": "Fruit", "tax_category_key": "product.generic"})
    for write in ("sale.department.delete", "sale.department.update"):
        field = fields_of(write, {"id": str(section.id)}, language)["id"]
        assert (field["value"], field["label"]) == ("Fruit", title)


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Quick note"), ("es", "Nota rápida")])
def test_a_quick_note_is_said_by_its_text_and_titled_as_its_screen(language, title):
    note = run("sale.quick_note.create", {"text": "No salt"})
    for write in ("sale.quick_note.delete", "sale.quick_note.update"):
        field = fields_of(write, {"id": str(note.id)}, language)["id"]
        assert (field["value"], field["label"]) == ("No salt", title)


@pytest.mark.django_db
def test_a_check_is_said_by_its_title(order):
    assert shown("sale.order.void", {"order_id": str(order.id)})["order_id"] == "Table 4"


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "total"), [("en", "€12.10"), ("es", "12,10 €")])
def test_a_check_with_no_title_is_said_by_its_amount_as_the_open_checks_list_does(shampoo, language, total):
    untitled = run("sale.order.open", {"lines": [{"product_id": str(shampoo.id)}]})
    assert flat(shown("sale.order.void", {"order_id": str(untitled.id)}, language)["order_id"]) == total


@pytest.mark.django_db
def test_the_two_checks_of_a_merge_are_said(shampoo, order):
    other = run("sale.order.open", {"label": "Table 9", "lines": [{"product_id": str(shampoo.id)}]})
    said = shown("sale.order.merge", {"from_order_id": str(order.id), "to_order_id": str(other.id)})
    assert said == {"from_order_id": "Table 4", "to_order_id": "Table 9"}


@pytest.mark.django_db
def test_a_line_of_a_check_is_said_by_its_name(order):
    line = str(order.lines[0].id)
    assert shown("sale.order.remove_line", {"order_id": str(order.id), "line_id": line})["line_id"] == "Shampoo"


@pytest.mark.django_db
def test_the_lines_a_split_moves_are_said_one_by_one(order):
    field = fields_of("sale.order.split", {"order_id": str(order.id), "line_ids": [str(order.lines[0].id)]})["line_ids"]
    assert field["value"] == ["Shampoo"]
    assert field[NAMED] is True


@pytest.mark.django_db
def test_a_sale_is_said_by_its_number(sale):
    said = shown("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong one"})
    assert said["sale_id"] == sale.number


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "method"), [("en", "Cash"), ("es", "Efectivo")])
def test_a_refund_says_the_tender_the_method_and_the_line_of_the_sale(sale, language, method):
    tender = sale.payments[0]
    other = next(row for row in run("sale.payment_method.list", {}).rows if row.id != tender.method_id)
    said = shown(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "Broken",
            "allocations": [{"payment_id": str(tender.id), "amount": 100, "to_method_id": str(other.id)}],
            "lines": [{"line_id": str(sale.lines[0].id)}],
        },
        language,
    )
    assert said["allocations"][0]["payment_id"] == method
    assert said["allocations"][0]["to_method_id"] and not AN_ID.search(said["allocations"][0]["to_method_id"])
    assert said["lines"] == [{"line_id": "Shampoo"}]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "method"), [("en", "Cash"), ("es", "Efectivo")])
def test_a_charge_says_the_payment_method_in_the_persons_language(shampoo, language, method):
    cash = next(row for row in run("sale.payment_method.list", {}).rows if row.type == "cash")
    said = shown(
        "sale.sale.complete",
        {"idempotency_key": KEY, "lines": [{"product_id": str(shampoo.id)}], "payments": [{"method_id": str(cash.id)}]},
        language,
    )
    assert said["payments"] == [{"method_id": method}]


@pytest.mark.django_db
def test_a_charge_says_the_customer_by_their_name(shampoo, customer):
    ana = customer("Ana López")
    said = shown(
        "sale.sale.complete",
        {"idempotency_key": KEY, "lines": [{"product_id": str(shampoo.id)}], "customer_id": str(ana.id)},
    )
    assert said["customer_id"] == "Ana López"


# ── What the apps Sales does not require name ─────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_line_says_its_product_and_who_serves_it(shampoo, order):
    bea = setup("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    said = shown(
        "sale.order.add_line",
        {"order_id": str(order.id), "product_id": str(shampoo.id), "staff_id": str(bea.id)},
    )
    assert (said["product_id"], said["staff_id"], said["order_id"]) == ("Shampoo", "Bea Ruiz", "Table 4")


@pytest.mark.django_db
def test_a_line_says_the_professional_a_write_gives_it(order):
    bea = setup("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    arguments = {"order_id": str(order.id), "line_id": str(order.lines[0].id), "staff_id": str(bea.id)}
    assert shown("sale.order.set_line_staff", arguments)["staff_id"] == "Bea Ruiz"


@pytest.mark.django_db
def test_a_line_says_its_modifiers_one_by_one(shampoo, order):
    setup("modifier.group.create", {"name": "Extras", "max_choices": 4})
    cheese = setup("modifier.option.create", {"group": "Extras", "name": "Cheese", "price_delta": 100})
    field = fields_of(
        "sale.order.add_line",
        {"order_id": str(order.id), "product_id": str(shampoo.id), "option_ids": [str(cheese.id)]},
    )["option_ids"]
    assert field["value"] == ["Cheese"]
    assert field[NAMED] is True


@pytest.mark.django_db
def test_a_section_of_an_open_price_line_is_said(order):
    section = run("sale.department.create", {"name": "Fruit", "tax_category_key": "product.generic"})
    said = shown(
        "sale.order.add_open_line",
        {"order_id": str(order.id), "unit_price": 100, "department_id": str(section.id)},
    )
    assert said["department_id"] == "Fruit"


@pytest.mark.django_db
def test_a_service_line_says_its_service(order):
    haircut = setup("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"})
    said = shown("sale.order.add_service_line", {"order_id": str(order.id), "service_id": str(haircut.id)})
    assert said["service_id"] == "Haircut"


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Section"), ("es", "Sección")])
def test_the_section_of_an_open_price_line_is_titled_as_its_screen(order, language, title):
    """Its model calls it a department; the screen and the card of the write that deletes one, a section."""
    department = run("sale.department.create", {"name": "Fruit", "tax_category_key": "product.generic"})
    arguments = {"order_id": str(order.id), "unit_price": 100, "department_id": str(department.id)}
    assert fields_of("sale.order.add_open_line", arguments, language)["department_id"]["label"] == title


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Service"), ("es", "Servicio")])
def test_the_service_of_a_line_is_titled_by_what_it_is_never_as_an_id(order, language, title):
    haircut = setup("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"})
    arguments = {"order_id": str(order.id), "service_id": str(haircut.id)}
    assert fields_of("sale.order.add_service_line", arguments, language)["service_id"]["label"] == title


@pytest.mark.django_db
def test_a_menu_line_says_its_menu_and_its_dishes(product, order):
    product("Lentils", "LEN", 500, "restaurant.food", initial_stock="10")
    setup("combo.combo.create", {"name": "Menu of the day", "price": 1350, "tax_category_key": "restaurant.food"})
    setup("combo.group.create", {"combo": "Menu of the day", "name": "Starters"})
    choice = setup("combo.option.create", {"combo": "Menu of the day", "group": "Starters", "product": "LEN"})
    menu = run("combo.combo.for_sale", {}, system_context(A)).rows[0]
    said = shown(
        "sale.order.add_combo_line",
        {"order_id": str(order.id), "combo_id": str(menu.id), "choices": [{"option_id": str(choice.id)}]},
    )
    assert said["combo_id"] == "Menu of the day"
    assert said["choices"] == [{"option_id": "Lentils"}]


@pytest.mark.django_db
def test_a_voucher_is_said_by_its_package(order, customer):
    haircut = setup("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"})
    package = setup(
        "service.package.create",
        {"name": "Five cuts", "max_uses": 5, "validity_days": None, "items": [{"service_id": str(haircut.id)}]},
    )
    grant = setup(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(customer("Lucía Pérez").id), "amount": 10000},
    )
    arguments = {"order_id": str(order.id), "line_id": str(order.lines[0].id), "grant_id": str(grant.id)}
    assert shown("sale.order.apply_voucher", arguments)["grant_id"] == "Five cuts"


@pytest.mark.django_db
def test_an_appointment_is_said_by_its_number(order, customer):
    haircut = setup("service.service.create", {"name": "Haircut", "price": 2000, "tax_category_key": "service.generic"})
    ana = setup("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    setup("service.assignment.assign", {"service_id": str(haircut.id), "member_id": str(ana.id)})
    from apps.schedule.models import ScheduleSettings, WeekDay

    WeekDay.objects.all().delete()
    ScheduleSettings.objects.all().delete()
    start = timezone.localtime() + dt.timedelta(days=7)
    booked = setup(
        "appointment.appointment.create",
        {
            "customer_id": str(customer("Lucía Pérez").id),
            "services": [{"service_id": str(haircut.id)}],
            "staff_id": str(ana.id),
            "start": start.replace(hour=10, minute=0, second=0, microsecond=0, tzinfo=None).isoformat(),
        },
    )
    said = shown("sale.order.set_appointment", {"order_id": str(order.id), "appointment_id": str(booked.id)})
    assert said["appointment_id"] == booked.number


# ── Never by its id ───────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_record_that_is_not_there_is_left_out_never_by_its_id(order):
    gone = str(uuid.uuid4())
    said = shown("sale.order.remove_line", {"order_id": gone, "line_id": gone})
    assert said == {}


@pytest.mark.django_db
def test_a_record_the_person_may_not_read_is_left_out_never_by_its_id(order):
    """The read of another app runs as whoever asks: without Staff's permission, its member stays out of the card."""
    bea = setup("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    allowed = ctx_for("hub_employee")
    denied = dataclasses.replace(allowed, permissions=allowed.permissions - {"staff.view"})
    arguments = {"order_id": str(order.id), "line_id": str(order.lines[0].id), "staff_id": str(bea.id)}
    assert shown("sale.order.set_line_staff", arguments, ctx=allowed)["staff_id"] == "Bea Ruiz"  # positive control
    said = shown("sale.order.set_line_staff", arguments, ctx=denied)
    assert "staff_id" not in said
    assert not AN_ID.search(str(said))


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        note = run("sale.quick_note.create", {"text": "No salt"}, in_a)
        assert shown("sale.quick_note.delete", {"id": str(note.id)}, ctx=in_a)["id"] == "No salt"  # positive control
    with use_hub(hub_b):
        assert shown("sale.quick_note.delete", {"id": str(note.id)}, ctx=in_b) == {}


# ── The read that names them ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_read_needs_the_right_to_see_sales():
    note = run("sale.quick_note.create", {"text": "No salt"})
    # Everything but this right, so it is this one the read asks for.
    everything = ctx_for()
    without = dataclasses.replace(everything, permissions=everything.permissions - {"sale.view_sale"})
    with pytest.raises(PermissionDenied):
        run("sale.record.get", {"quick_note_id": str(note.id)}, without)


@pytest.mark.parametrize("data", [{}, {"quick_note_id": str(uuid.uuid4()), "order_id": str(uuid.uuid4())}])
def test_the_read_takes_one_record(data):
    with pytest.raises(ValidationError):
        get("sale.record.get").input.model_validate(data)


@pytest.mark.django_db
def test_the_read_says_not_found_for_a_retired_record():
    note = run("sale.quick_note.create", {"text": "No salt"})
    QuickNote.objects.filter(pk=note.id).update(is_deleted=True)
    with pytest.raises(NotFound):
        run("sale.record.get", {"quick_note_id": str(note.id)})


@pytest.mark.django_db
def test_the_read_says_not_found_for_a_voided_line(order):
    line = order.lines[0].id
    OrderLine.objects.filter(pk=line).update(removed_at=timezone.now())
    with pytest.raises(NotFound):
        run("sale.record.get", {"line_id": str(line)})


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "said"), [("en", "Refund of sale {}"), ("es", "Devolución de la venta {}")])
def test_the_read_says_a_refund_by_the_sale_it_gives_back(sale, language, said):
    """A refund has no number of its own: «Sales» lists it under its sale (SALE-F31, SALE-F32). Services' card names by it
    the refund that gives back a voucher's sessions (hub#756)."""
    refund = run(
        "sale.sale.refund",
        {"sale_id": str(sale.id), "reason": "Broken", "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 100}]},
    )
    named = run("sale.record.get", {"refund_id": str(refund.refund_id)}, ctx_for(language=language))
    assert named.name == said.format(sale.number)


@pytest.mark.django_db
def test_the_read_says_not_found_for_a_refund_that_is_not_there(sale):
    """The id of a sale is no refund: the card of a void asks for the sale."""
    for missing in (str(uuid.uuid4()), str(sale.id)):
        with pytest.raises(NotFound) as caught:
            run("sale.record.get", {"refund_id": missing})
        assert caught.value.code == "sale.refund_not_found"


def test_the_read_is_no_tool_of_the_assistant():
    assert assistant.is_tool(get("sale.record.get")) is False


def test_an_input_the_read_does_not_take_is_refused():
    with pytest.raises((ValidationError, InvalidPayload)):
        get("sale.record.get").input.model_validate({"nothing": str(uuid.uuid4())})


# ── The closed lists ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("language", "value", "word"),
    [
        ("en", "dine_in", "Dine in"),
        ("en", "takeaway", "Takeaway"),
        ("en", "delivery", "Delivery"),
        ("es", "dine_in", "En sala"),
        ("es", "takeaway", "Para llevar"),
        ("es", "delivery", "A domicilio"),
    ],
)
@pytest.mark.django_db
def test_the_order_type_of_a_round_is_said_as_the_kitchen_says_it(order, language, value, word):
    said = shown("sale.order.fire", {"order_id": str(order.id), "channel": value}, language)
    assert said["channel"] == word


@pytest.mark.parametrize(
    ("language", "word"),
    [("en", "EU VAT number"), ("es", "NIF-IVA de la UE")],
)
@pytest.mark.parametrize("write", ["sale.sale.complete", "sale.sale.complete_over_limit"])
def test_the_kind_of_a_foreign_customers_document_is_said_in_words(write, language, word):
    said = shown(write, {"customer_id_type": "02"}, language)
    assert said["customer_id_type"] == word


def test_every_kind_of_document_a_charge_takes_has_its_word():
    assert tuple(ForeignIdType.values) == ID_TYPES
    assert get("sale.sale.complete").input.model_json_schema()["properties"]["customer_id_type"]["enum"] == [
        "",
        *ID_TYPES,
    ]

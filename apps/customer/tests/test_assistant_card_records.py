"""FIX-HUB-CUSTOMER-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#513): the card of a write of Customers says which
customer, group, tag, custom field or open order it acts on by its name, read as whoever asks, never by its id, and
leaves it out when that person may not read it or it is not there. The open order is Sales's: Customers needs no other
app, so it names it by Sales's own read, and without Sales the card leaves it out.
"""

import dataclasses

import pytest
from django.utils import timezone
from live.context import Scope
from live.errors import AppInactive, Conflict, NotFound, PermissionDenied
from live.operations import get, registry
from pydantic import ValidationError

from apps.customer.models import Customer, CustomerGroup, CustomerTag, CustomField
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

from .conftest import ctx_for

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"
#: Sales's read that names an open check, the one Customers asks for an order's name.
SALES_NAMES = "sale.record.get"


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for(language=language))
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def read(name: str, data: dict, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


def a_card(name: str = "Ana López", **fields) -> Customer:
    return Customer.objects.create(name=name, **fields)


def an_order(label: str = "Table 4"):
    """An open check of Sales, opened by its own operation."""
    op = get("sale.order.open")
    return op(ctx_for(), op.input.model_validate({"label": label}))


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


# ── A customer ────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Customer"), ("es", "Cliente")])
@pytest.mark.parametrize(
    ("write", "extra"),
    [
        ("customer.customer.update", {"city": "Madrid"}),
        ("customer.customer.delete", {}),
        ("customer.customer.erase", {}),
        ("customer.customer.set_groups", {}),
        ("customer.customer.set_tags", {}),
        ("customer.customer.merge", {"absorbed": "Ana Lopez"}),
    ],
)
def test_a_write_on_a_card_says_whose_it_is_and_titles_it_as_its_screens_do(write, extra, language, title):
    card = a_card()
    field = fields_of(write, {"id": str(card.id), **extra}, language)["id"]
    assert (field["value"], field["label"]) == ("Ana López", title)


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Customer"), ("es", "Cliente")])
@pytest.mark.parametrize(
    ("write", "extra"),
    [
        ("customer.note.add", {"content": "Window table"}),
        ("customer.activity.add", {"kind": "appointment.visit", "title": "Visit"}),
        ("customer.consent.grant", {"channel": "email", "notice_text": "May we email you?"}),
        ("customer.consent.withdraw", {"channel": "email"}),
    ],
)
def test_what_hangs_from_a_card_says_whose_card_it_is(write, extra, language, title):
    """The case the issue names: a note or an activity on the card, and its consent."""
    card = a_card()
    field = fields_of(write, {"customer_id": str(card.id), **extra}, language)["customer_id"]
    assert (field["value"], field["label"]) == ("Ana López", title)


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Duplicate customer"), ("es", "Ficha duplicada")])
def test_a_merge_says_the_card_that_stays_and_the_duplicate_by_their_names(language, title):
    stays, duplicate = a_card("Ana López"), a_card("Ana Lopez", phone="+34600111222")
    said = fields_of("customer.customer.merge", {"id": str(stays.id), "absorbed_id": str(duplicate.id)}, language)
    assert said["id"]["value"] == "Ana López"
    assert (said["absorbed_id"]["value"], said["absorbed_id"]["label"]) == ("Ana Lopez", title)


# ── Groups, tags and custom fields ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_groups_and_tags_a_card_is_given_go_by_their_names():
    """«Guardar grupos» and «Guardar etiquetas»: each one the card is given, never by its id."""
    card = a_card()
    vip, regulars = CustomerGroup.objects.create(name="VIP"), CustomerGroup.objects.create(name="Regulars")
    allergic = CustomerTag.objects.create(name="Allergic")
    groups = shown("customer.customer.set_groups", {"id": str(card.id), "group_ids": [str(vip.id), str(regulars.id)]})
    tags = shown("customer.customer.set_tags", {"id": str(card.id), "tag_ids": [str(allergic.id)]})
    assert groups["group_ids"] == ["VIP", "Regulars"]
    assert tags["tag_ids"] == ["Allergic"]
    assert no_id(groups) and no_id(tags)


@pytest.mark.django_db
def test_the_custom_fields_of_an_edited_card_go_by_their_names():
    card = a_card()
    allergies = CustomField.objects.create(name="Allergies")
    said = shown(
        "customer.customer.update", {"id": str(card.id), "field_values": [{"field_id": str(allergies.id), "value": "Nuts"}]}
    )
    assert said["field_values"] == [{"field_id": "Allergies", "value": "Nuts"}]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "group", "tag", "field"),
    [("en", "Group", "Tag", "Custom field"), ("es", "Grupo", "Etiqueta", "Campo personalizado")],
)
def test_a_write_on_a_group_a_tag_or_a_field_says_which_by_its_name(language, group, tag, field):
    """Also one no longer active, which a change brings back."""
    records = {
        "customer.group": (CustomerGroup.objects.create(name="VIP", is_active=False), group),
        "customer.tag": (CustomerTag.objects.create(name="Allergic"), tag),
        "customer.field": (CustomField.objects.create(name="Allergies"), field),
    }
    for entity, (record, title) in records.items():
        for action in ("update", "delete"):
            said = fields_of(f"{entity}.{action}", {"id": str(record.id)}, language)["id"]
            assert (said["value"], said["label"]) == (record.name, title), f"{entity}.{action}"


# ── An open order, by Sales's name for it ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Open order"), ("es", "Pedido abierto")])
def test_putting_a_customer_on_an_order_says_the_order_as_sales_names_it(language, title):
    card, order = a_card(), an_order("Table 4")
    said = fields_of("customer.order.link", {"order_id": str(order.id), "customer_id": str(card.id)}, language)
    assert (said["order_id"]["value"], said["order_id"]["label"]) == ("Table 4", title)
    assert said["customer_id"]["value"] == "Ana López"


@pytest.fixture(params=["off", "absent"])
def sales_unavailable(request, monkeypatch):
    """Sales, which Customers does not require, off in the business or not installed."""
    if request.param == "absent":
        monkeypatch.delitem(registry, SALES_NAMES)
    else:

        def off(ctx, data):
            raise AppInactive("Sales is off.")

        monkeypatch.setitem(registry, SALES_NAMES, dataclasses.replace(registry[SALES_NAMES], fn=off))


@pytest.mark.django_db
def test_without_sales_the_card_leaves_the_order_out_and_names_the_customer(sales_unavailable):
    card = a_card()
    said = shown("customer.order.link", {"order_id": A_MISSING_ID, "customer_id": str(card.id)})
    assert said == {"customer_id": "Ana López"}


@pytest.mark.django_db
def test_without_sales_the_read_of_an_order_says_sales_is_unavailable(sales_unavailable):
    with pytest.raises(Conflict) as caught:
        read("customer.order.get", {"order_id": A_MISSING_ID})
    assert caught.value.code == "customer.sales_unavailable"


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("needed", "write", "datum"),
    [
        ("customer.view", "customer.customer.delete", "id"),
        ("customer.view", "customer.note.add", "customer_id"),
        ("customer.view", "customer.group.delete", "id"),
        ("customer.view", "customer.tag.delete", "id"),
        ("customer.view", "customer.field.delete", "id"),
        ("customer.view", "customer.order.link", "order_id"),
        ("sale.view_sale", "customer.order.link", "order_id"),
    ],
)
def test_what_the_person_may_not_read_is_left_out_never_said_by_its_id(needed, write, datum):
    target = {
        "customer.customer.delete": a_card,
        "customer.note.add": a_card,
        "customer.group.delete": lambda: CustomerGroup.objects.create(name="VIP"),
        "customer.tag.delete": lambda: CustomerTag.objects.create(name="Allergic"),
        "customer.field.delete": lambda: CustomField.objects.create(name="Allergies"),
        "customer.order.link": an_order,
    }[write]()
    arguments = {datum: str(target.id), "content": "Window table"} if write == "customer.note.add" else {datum: str(target.id)}
    allowed = ctx_for()
    assert datum in shown(write, arguments, ctx=allowed)  # positive control
    said = shown(write, arguments, ctx=ctx_for(permissions=set(allowed.permissions) - {needed}))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("write", "datum"),
    [
        ("customer.customer.delete", "id"),
        ("customer.consent.withdraw", "customer_id"),
        ("customer.group.delete", "id"),
        ("customer.tag.delete", "id"),
        ("customer.field.delete", "id"),
        ("customer.order.link", "order_id"),
    ],
)
def test_what_does_not_exist_is_left_out(write, datum):
    extra = {"channel": "email"} if write == "customer.consent.withdraw" else {}
    said = shown(write, {datum: A_MISSING_ID, **extra})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_a_deleted_card_is_left_out_as_its_screens_leave_it_out():
    """Erasing the data of a card already deleted still works (CUSTOMER-F16), but no screen shows that card."""
    deleted = a_card(deleted_at=timezone.now())
    assert shown("customer.customer.erase", {"id": str(deleted.id)}) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    card, vip = a_card(), CustomerGroup.objects.create(name="VIP")
    write = get("customer.customer.set_groups")
    said = {field["name"]: field["value"] for field in assistant.card(write, {"id": str(card.id), "group_ids": [str(vip.id)]}, "en")["fields"]}
    assert said == {"group_ids": [None]}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        writes = [
            ("customer.customer.delete", a_card()),
            ("customer.group.delete", CustomerGroup.objects.create(name="VIP")),
            ("customer.tag.delete", CustomerTag.objects.create(name="Allergic")),
            ("customer.field.delete", CustomField.objects.create(name="Allergies")),
        ]
        for write, record in writes:  # positive control
            assert "id" in shown(write, {"id": str(record.id)}, ctx=in_a), write
    with use_hub(hub_b):
        for write, record in writes:
            assert shown(write, {"id": str(record.id)}, ctx=in_b) == {}, write


# ── A closed list, by the word of its screen ──────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", {"lifecycle_stage": "At risk", "source": "Referral", "preferred_channel": "WhatsApp"}),
        ("es", {"lifecycle_stage": "En riesgo", "source": "Recomendación", "preferred_channel": "WhatsApp"}),
    ],
)
def test_a_stage_a_source_and_a_channel_go_by_their_word_in_both_languages(language, expected):
    card = a_card()
    sent = {"lifecycle_stage": "at_risk", "source": "referral", "preferred_channel": "whatsapp"}
    said = shown("customer.customer.update", {"id": str(card.id), **sent}, language)
    assert {name: said[name] for name in sent} == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "channel", "source"), [("en", "Post", "Web form"), ("es", "Correo postal", "Formulario web")]
)
def test_a_consent_says_its_channel_and_where_it_was_given_in_both_languages(language, channel, source):
    card = a_card()
    sent = {"customer_id": str(card.id), "channel": "postal", "source": "web_form", "notice_text": "May we write?"}
    said = shown("customer.consent.grant", sent, language)
    assert (said["channel"], said["source"]) == (channel, source)


# ── The reads that name them ──────────────────────────────────────────────────────────────────────────────────────────

READS = ["customer.group.detail", "customer.tag.detail", "customer.field.detail", "customer.order.get"]


@pytest.mark.django_db
def test_the_reads_answer_the_name_of_what_they_read():
    vip = CustomerGroup.objects.create(name="VIP")
    allergic = CustomerTag.objects.create(name="Allergic")
    allergies = CustomField.objects.create(name="Allergies")
    order = an_order("Table 4")
    assert read("customer.group.detail", {"id": str(vip.id)}).name == "VIP"
    assert read("customer.tag.detail", {"id": str(allergic.id)}).name == "Allergic"
    assert read("customer.field.detail", {"id": str(allergies.id)}).name == "Allergies"
    assert read("customer.order.get", {"order_id": str(order.id)}).name == "Table 4"


@pytest.mark.django_db
@pytest.mark.parametrize("name", READS)
def test_the_reads_need_the_right_to_see_the_customers(name):
    denied = ctx_for(permissions=set(ctx_for().permissions) - {"customer.view"})
    key = "order_id" if name == "customer.order.get" else "id"
    with pytest.raises(PermissionDenied):
        read(name, {key: A_MISSING_ID}, denied)


@pytest.mark.django_db
@pytest.mark.parametrize("name", READS)
def test_the_reads_say_not_found_for_what_is_not_there(name):
    key = "order_id" if name == "customer.order.get" else "id"
    with pytest.raises(NotFound):
        read(name, {key: A_MISSING_ID})


@pytest.mark.parametrize("name", READS)
def test_the_reads_refuse_no_id(name):
    with pytest.raises(ValidationError):
        get(name).input.model_validate({})


@pytest.mark.parametrize("name", READS)
def test_the_reads_are_no_tool_of_the_assistant(name):
    """The model finds them in its lists; only the card reads them."""
    assert not assistant.is_tool(get(name))

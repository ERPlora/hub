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

from apps.customer.models import Activity, Customer, CustomerGroup, CustomerTag, CustomField
from apps.customer.schemas import A_CUSTOMER_REFERENCE
from base import assistant
from base.schemas import names
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID
from base.tests.test_assistant_yes_for_its_card import unless_marked, yes_to_its_card

from .conftest import ctx_for
from .test_integration_assistant import customer_writes

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


# ── A card that comes by its id with the name of another one beside it (hub#1272) ─────────────────────────────────────
# A merge takes each card by its id when it comes (``find_customer``) and never looks at the name said beside it: the
# card neither reads nor shows that name (``unless``, hub#1250), never «Cliente: Bea Ruiz» beside «Cliente: Ana López»
# when the merge keeps Ana López. Each name is left unread only beside its own card's id: the duplicate's id says
# nothing of the card that stays, nor the other way round.

#: Beside which data each write of Customers takes its card by them and not by the name said beside them.
UNLESS = {
    ("customer.customer.merge", "customer"): {"id"},
    ("customer.customer.merge", "absorbed"): {"absorbed_id"},
}


def test_a_name_is_left_unread_beside_the_id_its_write_takes_the_card_by_instead():
    assert unless_marked(customer_writes(), A_CUSTOMER_REFERENCE) == UNLESS


def by_their_ids_beside_other_names() -> tuple[dict, Customer]:
    """A merge of «Ana Lopez» into «Ana López» by their ids, with the names of two other cards beside them. → its data
    and the card that stays."""
    stays, duplicate = a_card("Ana López"), a_card("Ana Lopez")
    a_card("Bea Ruiz")
    a_card("Carla Gil")
    arguments = {"id": str(stays.id), "customer": "Bea Ruiz", "absorbed_id": str(duplicate.id), "absorbed": "Carla Gil"}
    return arguments, stays


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_merge_by_ids_names_only_the_two_cards_it_merges_whatever_names_come_beside_them(language):
    arguments, _ = by_their_ids_beside_other_names()
    assert shown("customer.customer.merge", arguments, language) == {"id": "Ana López", "absorbed_id": "Ana Lopez"}


@pytest.mark.django_db
def test_a_name_beside_the_id_of_the_other_card_is_still_read():
    """The card that stays said by its name beside the duplicate's id, and the duplicate said by its name beside the id
    of the one that stays: each is the card the merge finds by that name."""
    stays, duplicate = a_card("Ana López"), a_card("Ana Lopez")
    a_card("Bea Ruiz")
    a_card("Carla Gil")
    by_name_and_id = {"customer": "Bea Ruiz", "absorbed_id": str(duplicate.id)}
    assert shown("customer.customer.merge", by_name_and_id) == {"customer": "Bea Ruiz", "absorbed_id": "Ana Lopez"}
    by_id_and_name = {"id": str(stays.id), "absorbed": "Carla Gil"}
    assert shown("customer.customer.merge", by_id_and_name) == {"id": "Ana López", "absorbed": "Carla Gil"}


@pytest.mark.django_db
def test_the_yes_to_a_merge_by_ids_merges_those_two_cards_whatever_names_come_beside_them():
    """Control of the above: the merge keeps the card of ``id`` and absorbs the one of ``absorbed_id``; the cards the
    names beside them fit are not touched."""
    arguments, stays = by_their_ids_beside_other_names()
    done = yes_to_its_card(ctx_for(language="es"), "customer.customer.merge", arguments)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    merged = dict(Customer.objects.values_list("name", "merged_into_id"))
    assert merged == {"Ana López": None, "Ana Lopez": stays.id, "Bea Ruiz": None, "Carla Gil": None}


# ── A card, a group, a tag or a field said in words beside its own record's id (hub#1280) ─────────────────────────────
# Every other write of Customers takes its card, group, tag or custom field by its id when it comes (``find_customer``,
# ``find_group``, ``find_tag``, ``find_field``) and never looks at the words said beside it: the card neither reads nor
# shows them, never «Cliente: Bea Ruiz» beside «Cliente: Ana López». Said alone, the words are read as the write finds
# them (a card by its email says the card's name) and, when they fit none, they are said as said, as before; what they
# found goes in the fingerprint of the yes (BASE-F97).

#: How the card reads a card, a group, a tag or a custom field said in words: by the read that names it, with those
#: words, and as said when it cannot read them.
SAID = {
    "customer": names("customer.customer.detail", by="customer", as_said=True),
    "group": names("customer.group.detail", by="group", as_said=True),
    "tag": names("customer.tag.detail", by="tag", as_said=True),
    "field": names("customer.field.detail", by="field", as_said=True),
}
ON_A_CARD = ("delete", "erase", "set_groups", "set_tags", "update")
OF_A_CARD = (
    "customer.activity.add",
    "customer.consent.grant",
    "customer.consent.withdraw",
    "customer.note.add",
    "customer.order.link",
)
#: Beside which datum each write takes its record by it and not by the words said beside it.
UNLESS_SAID = {
    **{(f"customer.customer.{action}", "customer"): {"id"} for action in ON_A_CARD},
    **{(write, "customer"): {"customer_id"} for write in OF_A_CARD},
    **{
        (f"customer.{entity}.{action}", entity): {"id"}
        for entity in ("group", "tag", "field")
        for action in ("delete", "update")
    },
}
#: What each write needs besides its record.
EXTRA = {
    "customer.customer.update": {"city": "Madrid"},
    "customer.note.add": {"content": "Window table"},
    "customer.activity.add": {"kind": "appointment.visit", "title": "Visit"},
    "customer.consent.grant": {"channel": "email", "notice_text": "May we email you?"},
    "customer.consent.withdraw": {"channel": "email"},
    "customer.order.link": {"order_id": A_MISSING_ID},
    "customer.group.update": {"color": "#ff0000"},
    "customer.tag.update": {"color": "#ff0000"},
    "customer.field.update": {"is_required": True},
}
MODELS = {"customer": Customer, "group": CustomerGroup, "tag": CustomerTag, "field": CustomField}


def two(kind: str) -> tuple:
    """A record of ``kind`` a write takes by its id, and another one whose name may come beside that id."""
    if kind == "customer":
        return a_card("Ana López", email="ana@example.com"), a_card("Bea Ruiz", email="bea@example.com")
    first, second = {"group": ("Regulars", "VIP"), "tag": ("Punctual", "Allergic"), "field": ("Size", "Allergies")}[kind]
    return MODELS[kind].objects.create(name=first), MODELS[kind].objects.create(name=second)


def words_for(kind: str, record) -> str:
    """What a person says for ``record``, as its write finds it: a card by its email, the rest by their name in any
    case."""
    return record.email if kind == "customer" else record.name.lower()


def test_words_said_beside_their_own_record_s_id_are_left_unread_beside_it():
    marked = [unless_marked(customer_writes(), mark) for mark in SAID.values()]
    assert {key: value for table in marked for key, value in table.items()} == UNLESS_SAID


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(("write", "datum"), sorted(UNLESS_SAID))
def test_a_record_by_its_id_beside_the_words_of_another_is_the_only_one_its_card_says(write, datum, language):
    (id_datum,) = UNLESS_SAID[write, datum]
    own, other = two(datum)
    said = shown(write, {id_datum: str(own.id), datum: other.name, **EXTRA.get(write, {})}, language)
    assert (said.get(id_datum), datum in said) == (own.name, False)


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), sorted(UNLESS_SAID))
def test_words_said_alone_name_the_record_their_write_finds_by_them(write, datum):
    own, _ = two(datum)
    said = shown(write, {datum: words_for(datum, own), **EXTRA.get(write, {})}, "es")
    assert said[datum] == own.name


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), sorted(UNLESS_SAID))
def test_words_that_fit_no_record_are_said_as_said(write, datum):
    """As before the mark: the card says what was said, and the write answers that nothing fits."""
    said = shown(write, {datum: "Nobody", **EXTRA.get(write, {})}, "es")
    assert said[datum] == "Nobody"


@pytest.mark.django_db
def test_words_that_fit_several_cards_are_said_as_said():
    a_card("Ana López")
    a_card("Ana López")
    assert shown("customer.customer.delete", {"customer": "Ana López"}, "es") == {"customer": "Ana López"}


def touched(write: str, kind: str) -> object:
    """What ``write`` leaves behind, to tell which record it touched."""
    if write == "customer.note.add":
        return sorted(Activity.objects.filter(kind=Activity.Kind.NOTE_ADDED).values_list("customer__name", flat=True))
    if kind == "customer":
        return sorted(Customer.objects.live().values_list("name", flat=True))
    return sorted(MODELS[kind].objects.values_list("name", flat=True))


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("write", "datum", "after"),
    [
        ("customer.customer.delete", "customer", ["Bea Ruiz"]),
        ("customer.note.add", "customer", ["Ana López"]),
        ("customer.group.delete", "group", ["VIP"]),
        ("customer.tag.delete", "tag", ["Allergic"]),
        ("customer.field.delete", "field", ["Allergies"]),
    ],
)
def test_the_yes_touches_only_the_record_of_the_id_whatever_words_come_beside_it(write, datum, after):
    """Control of the above: the write acts on the record of the id; the one the words beside it fit is not touched."""
    (id_datum,) = UNLESS_SAID[write, datum]
    own, other = two(datum)
    arguments = {id_datum: str(own.id), datum: other.name, **EXTRA.get(write, {})}
    done = yes_to_its_card(ctx_for(language="es"), write, arguments)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert touched(write, datum) == after


@pytest.mark.django_db
def test_the_yes_to_a_card_said_by_its_email_deletes_it():
    """Control: nothing changed between the card and the yes."""
    ana, _ = two("customer")
    done = yes_to_its_card(ctx_for(language="es"), "customer.customer.delete", {"customer": ana.email})
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert touched("customer.customer.delete", "customer") == ["Bea Ruiz"]


@pytest.mark.django_db
def test_the_yes_deletes_nobody_when_the_email_its_card_was_said_by_is_another_card_s_meanwhile():
    """The card said «Cliente: Ana López» for ana@example.com; before the yes, that email moves to Bea Ruiz: the yes
    deletes neither, and the card is drawn again."""
    ana, bea = two("customer")

    def meanwhile():
        Customer.objects.filter(pk=ana.pk).update(email="")
        Customer.objects.filter(pk=bea.pk).update(email=ana.email)

    done = yes_to_its_card(ctx_for(language="es"), "customer.customer.delete", {"customer": ana.email}, meanwhile)
    assert done["executed"] == []
    assert touched("customer.customer.delete", "customer") == ["Ana López", "Bea Ruiz"]


@pytest.mark.django_db
def test_the_yes_deletes_no_group_when_another_fits_its_name_better_meanwhile():
    """A group no longer active said by its name; before the yes, somebody creates an active one with that name, which
    the write would take instead: the yes deletes neither."""
    CustomerGroup.objects.create(name="VIP", is_active=False)
    done = yes_to_its_card(
        ctx_for(language="es"),
        "customer.group.delete",
        {"group": "VIP"},
        lambda: CustomerGroup.objects.create(name="VIP"),
    )
    assert done["executed"] == []
    assert CustomerGroup.objects.filter(name="VIP").count() == 2


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


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_words_that_fit_a_record_of_another_business_are_said_as_said(hub_a, hub_b):
    """Each business in its own database: the words that name a record of A name nothing in B (hub#1280)."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    writes = ["customer.customer.delete", "customer.group.delete", "customer.tag.delete", "customer.field.delete"]
    said = []
    with use_hub(hub_a):
        for write in writes:
            kind = write.split(".")[1]
            own, _ = two(kind)
            said.append((write, kind, words_for(kind, own)))
            assert shown(write, {kind: said[-1][2]}, ctx=in_a) == {kind: own.name}, write  # positive control
    with use_hub(hub_b):
        for write, kind, words in said:
            assert shown(write, {kind: words}, ctx=in_b) == {kind: words}, write


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
@pytest.mark.parametrize("kind", ["group", "tag", "field"])
def test_the_reads_find_a_group_a_tag_or_a_field_by_its_name_as_their_writes_do(kind):
    """In any case, the active one before one no longer active, as ``find_group`` and its neighbours find it (hub#1280);
    a name that fits none is not found."""
    MODELS[kind].objects.create(name="VIP", is_active=False)
    active = MODELS[kind].objects.create(name="vip")
    assert read(f"customer.{kind}.detail", {kind: "Vip"}).id == active.id
    with pytest.raises(NotFound):
        read(f"customer.{kind}.detail", {kind: "Nobody"})


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["group", "tag", "field"])
def test_the_reads_take_a_group_a_tag_or_a_field_by_its_id_whatever_name_comes_beside_it(kind):
    """The id wins, as in their writes (``_find_named``)."""
    own, other = two(kind)
    assert read(f"customer.{kind}.detail", {"id": str(own.id), kind: other.name}).id == own.id


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

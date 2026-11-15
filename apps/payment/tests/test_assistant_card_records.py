"""hub#674: the card of a write of Payments says which payment or method it acts on by its name, read as whoever asks,
never by an id, and leaves it out when that person may not read it or it is not there. A payment goes by its reference
and a method by its name, as the screens say them («Cancel payment — PAY-20261014-0003», «Editing method — BBVA
account»), under the word each list calls one.
"""

import dataclasses
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import get, registry

from apps.payment.tests.conftest import A, ctx_for, make_method, make_payment
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import technical_names
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

SCREENS = Path(apps.get_app_config("payment").path) / "frontend/locale"

#: The writes on one method named by its id.
ON_A_METHOD = ["payment.method.activate", "payment.method.deactivate", "payment.method.update"]
#: The writes on one payment named by its id.
ON_A_PAYMENT = [
    "payment.payment.approve",
    "payment.payment.cancel",
    "payment.payment.mark_completed",
    "payment.payment.mark_sent",
]


def screens(language: str) -> dict:
    return json.loads((SCREENS / f"{language}.json").read_text())["payment"]


def one(language: str, entity: str) -> str:
    """What the list of ``entity`` (``payments``, ``methods``) calls one, as a title: «Pago», «Método»."""
    return screens(language)[entity]["entity"]["one"].capitalize()


def as_admin(language: str = "en", scope: Scope = A) -> OperationContext:
    return dataclasses.replace(ctx_for(scope=scope), language=language)


def without(permissions: set[str], language: str = "en") -> OperationContext:
    """An admin without ``permissions``: a combination no role has."""
    ctx = as_admin(language)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - permissions)


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or as_admin(language))
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


def payment_writes() -> list:
    return [
        op
        for _, op in sorted(registry.items())
        if op.app_label == "payment" and op.kind == "command" and assistant.is_tool(op)
    ]


@dataclasses.dataclass
class Books:
    """Two methods and a payment from each, every datum that could name them filled: a method's name and its account;
    a payment's reference, beneficiary, IBAN, concept and supplier's invoice."""

    bbva: object
    drawer: object
    rent: object
    flour: object


def make_books() -> Books:
    bbva = make_method("BBVA account", "transfer", bank_account_ref="ES91 2100 0418 4502 0005 1332")
    drawer = make_method("Cash drawer", "cash", bank_account_ref="DRAWER-1")
    rent = make_payment(
        bbva,
        reference="PAY-20261014-0001",
        beneficiary_name="Inmobiliaria Sol SL",
        beneficiary_iban="ES9121000418450200051332",
        concept="October rent",
        supplier_invoice_ref="FAC-2026-118",
    )
    flour = make_payment(
        drawer,
        reference="PAY-20261014-0002",
        beneficiary_name="Harinas del Norte SL",
        beneficiary_iban="ES7921000813610123456789",
        concept="Flour",
        supplier_invoice_ref="HN-77",
    )
    return Books(bbva, drawer, rent, flour)


# ── A method, by its name; a payment, by its reference ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("write", ON_A_METHOD)
def test_a_write_on_a_method_says_it_by_its_name_as_the_methods_list_calls_one(write, language):
    """The case the issue names, «payment.method.activate:id»: the method by its name, under the word the methods
    list calls one («Método»), as the edit form says it («Editing method — BBVA account»)."""
    books = make_books()
    field = fields_of(write, {"id": str(books.bbva.id)}, language).get("id", {})
    assert (field.get("value"), field.get("label")) == ("BBVA account", one(language, "methods"))


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("write", ON_A_PAYMENT)
def test_a_write_on_a_payment_says_it_by_its_reference_as_the_payments_list_calls_one(write, language):
    """A payment by its reference, under the word the payments list calls one («Pago»), as the cancel form says it
    («Cancel payment — PAY-20261014-0001»)."""
    books = make_books()
    field = fields_of(write, {"id": str(books.rent.id)}, language).get("id", {})
    assert (field.get("value"), field.get("label")) == ("PAY-20261014-0001", one(language, "payments"))


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_new_payment_says_the_method_it_leaves_from_by_its_name(language):
    books = make_books()
    sent = {
        "method_id": str(books.drawer.id),
        "payment_date": "2026-10-14",
        "amount": 1250,
        "beneficiary_name": "Harinas del Norte SL",
    }
    field = fields_of("payment.payment.create", sent, language).get("method_id", {})
    title = {"en": "Method", "es": "Método"}[language]
    assert (field.get("value"), field.get("label")) == ("Cash drawer", title)


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own method or payment, never another of the list (the first, the last, the newest)."""
    books = make_books()
    methods = [shown("payment.method.deactivate", {"id": str(method.id)}) for method in (books.drawer, books.bbva)]
    assert methods == [{"id": "Cash drawer"}, {"id": "BBVA account"}]
    payments = [shown("payment.payment.approve", {"id": str(payment.id)}) for payment in (books.flour, books.rent)]
    assert payments == [{"id": "PAY-20261014-0002"}, {"id": "PAY-20261014-0001"}]
    created = [
        shown("payment.payment.create", {"method_id": str(method.id), "amount": 100}).get("method_id")
        for method in (books.bbva, books.drawer)
    ]
    assert created == ["BBVA account", "Cash drawer"]


@pytest.mark.django_db
def test_a_cancellation_says_the_payment_beside_its_reason():
    books = make_books()
    said = shown("payment.payment.cancel", {"id": str(books.flour.id), "reason": "Duplicado"}, "es")
    assert said == {"id": "PAY-20261014-0002", "reason": "Duplicado"}


@pytest.mark.django_db
def test_an_edit_says_the_method_beside_what_changes_with_its_type_in_each_language():
    """The method by its name; its new type by the label the methods form gives it, never as sent («transfer»)."""
    books = make_books()
    sent = {"id": str(books.drawer.id), "name": "Caja", "method_type": "transfer"}
    assert shown("payment.method.update", sent, "en") == {"id": "Cash drawer", "name": "Caja", "method_type": "Bank transfer"}
    assert shown("payment.method.update", sent, "es") == {"id": "Cash drawer", "name": "Caja", "method_type": "Transferencia"}


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("write", [*ON_A_METHOD, *ON_A_PAYMENT])
def test_what_the_person_may_not_read_is_left_out_never_said_by_its_id(write):
    """Whoever may not read the payments is told no method nor payment: both reads ask for ``view_payment``."""
    books = make_books()
    record = books.bbva if write in ON_A_METHOD else books.rent
    arguments = {"id": str(record.id)}
    assert "id" in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without({"payment.view_payment"}))
    assert said == {}
    assert no_id(said)


@pytest.mark.django_db
def test_a_method_the_person_may_not_read_is_left_out_of_a_new_payment():
    books = make_books()
    sent = {"method_id": str(books.bbva.id), "amount": 100}
    assert shown("payment.payment.create", sent).get("method_id") == "BBVA account"  # positive control
    said = shown("payment.payment.create", sent, ctx=without({"payment.view_payment"}))
    assert "method_id" not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize("write", [*ON_A_METHOD, *ON_A_PAYMENT])
def test_a_record_that_does_not_exist_is_left_out(write):
    make_books()
    assert shown(write, {"id": A_MISSING_ID}) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no method nor payment: nothing is read."""
    books = make_books()
    arguments = {"id": str(books.rent.id), "reason": "Duplicado"}
    assert shown("payment.payment.cancel", arguments)["id"] == "PAY-20261014-0001"  # positive control
    card = assistant.card(get("payment.payment.cancel"), arguments, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"reason": "Duplicado"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = as_admin(scope=Scope("host", hub_a.slug)), as_admin(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        books = make_books()
        on_the_method, on_the_payment = {"id": str(books.bbva.id)}, {"id": str(books.rent.id)}
        assert shown("payment.method.activate", on_the_method, ctx=in_a) == {"id": "BBVA account"}  # positive control
        assert shown("payment.payment.approve", on_the_payment, ctx=in_a) == {"id": "PAY-20261014-0001"}
    with use_hub(hub_b):
        assert shown("payment.method.activate", on_the_method, ctx=in_b) == {}
        assert shown("payment.payment.approve", on_the_payment, ctx=in_b) == {}


# ── Titles: every datum by a word of its own ──────────────────────────────────────────────────────────────────────────


def test_no_write_of_payment_goes_by_the_title_pydantic_makes_up():
    """The platform's check (``technical_names``, hub#892): no datum of a write of Payments reaches a Spanish card by
    the title pydantic makes up from its field («Id», «Method Id»)."""
    assert technical_names(payment_writes()) == {}


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_record_a_write_names_is_titled_with_the_screens_word_in_each_language(language):
    """``technical_names`` sends no person, so a marked datum is out of its card and it never sees its title: each
    marked id, with a real record, is called as its list calls one, in each language, and is said by its name."""
    books = make_books()
    titles = {}
    for op in payment_writes():
        props = op.input.model_json_schema().get("properties", {})
        for datum, record in (("id", books.bbva if op.name.startswith("payment.method.") else books.rent),
                              ("method_id", books.drawer)):
            if datum in props:
                field = fields_of(op.name, {datum: str(record.id)}, language).get(datum, {})
                titled = bool(field.get("titled"))  # the card leaves the key out of a datum its app gives no title
                titles[f"{op.name}:{datum}"] = (field.get("label"), titled, no_id(field.get("value")))
    method, payment = one(language, "methods"), one(language, "payments")
    assert titles == {
        **{f"{write}:id": (method, True, True) for write in ON_A_METHOD},
        **{f"{write}:id": (payment, True, True) for write in ON_A_PAYMENT},
        "payment.payment.create:method_id": ({"en": "Method", "es": "Método"}[language], False, True),
    }

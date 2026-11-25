"""Importing cards from a file: what it takes, what it skips and why (CUSTOMER-F08)."""

from django.utils import timezone

from apps.customer import events
from apps.customer.models import Customer
from apps.customer.schemas.importing import ImportIn
from apps.customer.services.importing import ALREADY_IMPORTED

from .conftest import HUB_DB, clear_outbox, outbox, run

pytestmark = HUB_DB


# customer.customer.import (CUSTOMER-F08; wasm_handlers.hub bulk_create)


def test_import_creates_the_good_rows_and_skips_the_bad_ones_with_their_reason():
    result = run(
        "customer.customer.import",
        ImportIn(
            rows=[
                {
                    "name": "Ana",
                    "phone": "600 111 222",
                    "email": "ana@example.com",
                    "country": "es",
                },
                {"name": "", "email": "nobody@example.com"},
                {"name": "Bea", "email": "bea@"},
                {"name": "Carla", "phone": "600111"},
                {"name": "Dora", "country": "Spain", "lifecycle_stage": "customer"},
                {
                    "name": "Eva",
                    "lifecycle_stage": "vip",
                    "source": "referral",
                    "birthday": "1990-05-04",
                },
                {"name": "Fran", "lifecycle_stage": "boss"},
            ]
        ),
        "hub_employee",
    )
    assert (result.created, result.skipped) == (3, 4)
    assert [
        (row.index, row.id is not None, sorted(row.errors), sorted(row.warnings))
        for row in result.rows
    ] == [
        (0, True, [], []),
        (1, False, ["name"], []),
        (2, False, ["email"], []),
        (3, False, ["phone"], []),
        (4, True, [], []),
        (5, True, [], []),
        (6, False, ["lifecycle_stage"], []),
    ]
    assert str(result.rows[3].errors["phone"]).startswith(
        "This is not a valid phone number"
    )
    ana, dora, eva = (
        Customer.objects.get(name=name) for name in ("Ana", "Dora", "Eva")
    )
    assert (ana.phone, ana.country, ana.source, ana.lifecycle_stage) == (
        "+34600111222",
        "ES",
        "import",
        "active",
    )
    # A country named in English or Spanish is read as its code, as the screen does.
    assert (dora.country, dora.lifecycle_stage) == ("ES", "active")
    assert (eva.source, eva.lifecycle_stage, eva.birthday) == (
        "referral",
        "vip",
        "1990-05-04",
    )
    # One notice per created card, as a creation by hand: WhatsApp links their conversations.
    assert outbox() == [
        (events.CUSTOMER_CREATED, {"id": str(row.id)}) for row in result.rows if row.id
    ]


def test_import_reads_a_country_by_its_code_or_its_name_and_warns_when_it_names_none():
    # The same reading as the screen, for an import through the API or the assistant: a code, a name
    # in Spanish or English (case and accents aside), the Spanish regions as Spain; else, a warning.
    result = run(
        "customer.customer.import",
        ImportIn(
            rows=[
                {"name": "A", "country": "fr"},
                {"name": "B", "country": "España"},
                {"name": "C", "country": "alemania"},
                {"name": "D", "country": "United Kingdom"},
                {"name": "E", "country": "IC"},
                {"name": "F", "country": "Narnia"},
                {"name": "G", "country": "XK"},
            ]
        ),
    )
    assert result.created == 7
    assert [sorted(row.warnings) for row in result.rows] == [
        [],
        [],
        [],
        [],
        [],
        ["country"],
        ["country"],
    ]
    assert dict(Customer.objects.values_list("name", "country")) == {
        "A": "FR",
        "B": "ES",
        "C": "DE",
        "D": "GB",
        "E": "ES",
        "F": "",
        "G": "",
    }


def test_import_takes_back_the_apostrophe_the_export_puts_in_front_of_a_formula():
    run(
        "customer.customer.import",
        ImportIn(rows=[{"name": "'=Ana", "phone": "'+34600111222"}]),
    )
    ana = Customer.objects.get()
    assert (ana.name, ana.phone) == ("=Ana", "+34600111222")


def test_importing_the_same_file_again_creates_nothing_new():
    """A file imported twice (or a row repeated in it) does not duplicate."""
    rows = [
        {"name": "Ana", "phone": "600 111 222", "email": "ana@example.com"},
        # Her daughter: the same phone, another person (CUSTOMER-F12): she is created.
        {"name": "Lucía", "phone": "600 111 222"},
        # The same row twice in the file: the second one is the same card.
        {"name": "Ana", "phone": "600111222", "email": "ana@example.com"},
    ]
    first = run("customer.customer.import", ImportIn(rows=rows))
    assert (first.created, first.skipped) == (2, 1)
    assert first.rows[2].errors == {"name": str(ALREADY_IMPORTED)}
    clear_outbox()
    # The same people typed another way: case, spaces and the phone with its prefix.
    again = run(
        "customer.customer.import",
        ImportIn(
            rows=[
                {
                    "name": " ana ",
                    "phone": "+34 600 111 222",
                    "email": "ANA@example.com",
                },
                {"name": "Lucía", "phone": "0034600111222"},
                # One of the three differs: not the same card, it is created.
                {"name": "Ana", "phone": "600111222", "email": "ana.work@example.com"},
                {"name": "Ana", "phone": "600 222 333", "email": "ana@example.com"},
                {"name": "Marta", "phone": "600111222"},
            ]
        ),
    )
    assert (again.created, again.skipped) == (3, 2)
    assert [row.errors for row in again.rows[:2]] == [
        {"name": str(ALREADY_IMPORTED)}
    ] * 2
    assert Customer.objects.count() == 5
    assert outbox() == [
        (events.CUSTOMER_CREATED, {"id": str(row.id)}) for row in again.rows[2:]
    ]
    # Only a live card is in the way: a deleted one is imported again.
    Customer.objects.filter(name="Lucía").update(deleted_at=timezone.now())
    third = run(
        "customer.customer.import",
        ImportIn(rows=[{"name": "Lucía", "phone": "600111222"}]),
    )
    assert (third.created, third.skipped) == (1, 0)

"""Creating and updating a customer's card (CUSTOMER-F01, F04), and its birthday and anniversary: a day and a month are
enough, the year only when it is known, and the card keeps and gives back exactly what was written."""

import pytest
from live.errors import InvalidPayload, NotFound

from apps.customer import events
from apps.customer.models import Customer
from apps.customer.schemas.cards import CustomerIn, CustomerPatchIn
from apps.customer.schemas.importing import ImportIn
from apps.customer.schemas.merging import MergeIn

from .conftest import HUB_DB, NOW, card, invalid, outbox, run

pytestmark = HUB_DB


def test_a_new_card_keeps_a_birthday_without_its_year():
    detail = run("customer.customer.create", CustomerIn(name="Lucía", birthday="--03-14", anniversary="2015-06-01"))
    assert (detail.birthday, detail.anniversary) == ("--03-14", "2015-06-01")
    assert Customer.objects.values_list("birthday", "anniversary").get(pk=detail.id) == ("--03-14", "2015-06-01")


def test_editing_a_card_sets_and_clears_a_day_without_its_year():
    lucia = Customer.objects.create(name="Lucía", birthday="1990-03-14")
    detail = run("customer.customer.update", CustomerPatchIn(id=lucia.id, birthday="--03-14", anniversary="--06-01"))
    assert (detail.birthday, detail.anniversary) == ("--03-14", "--06-01")
    detail = run("customer.customer.update", CustomerPatchIn(id=lucia.id, birthday=None, anniversary=""))
    assert (detail.birthday, detail.anniversary) == (None, None)
    lucia.refresh_from_db()
    assert (lucia.birthday, lucia.anniversary) == (None, None)


def test_an_import_takes_a_birthday_without_its_year_and_skips_a_day_that_does_not_exist():
    result = run(
        "customer.customer.import",
        ImportIn(rows=[{"name": "Lucía", "birthday": " --03-14 "}, {"name": "Marta", "anniversary": "--02-30"}]),
        "hub_employee",
    )
    assert [(row.id is not None, sorted(row.errors)) for row in result.rows] == [(True, []), (False, ["anniversary"])]
    assert Customer.objects.values_list("name", "birthday", "anniversary").get() == ("Lucía", "--03-14", None)


def test_merging_fills_an_empty_day_from_the_duplicate_and_keeps_its_own():
    lucia = Customer.objects.create(name="Lucía", anniversary="2015-06-01")
    twin = Customer.objects.create(name="Lucía M.", birthday="--03-14", anniversary="--09-09")
    detail = run("customer.customer.merge", MergeIn(id=lucia.id, absorbed_id=twin.id), "hub_owner")
    assert (detail.birthday, detail.anniversary) == ("--03-14", "2015-06-01")


# customer.customer.create (CUSTOMER-F01, F18, F26; create_walk_in.pg, phone_e164.hub)


def test_a_walk_in_is_created_from_a_name_and_announced():
    detail = run("customer.customer.create", CustomerIn(name="Ana"), "hub_employee")
    customer = Customer.objects.get()
    assert (
        detail.id,
        detail.name,
        detail.lifecycle_stage,
        detail.source,
        detail.preferred_channel,
    ) == (
        customer.id,
        "Ana",
        "lead",
        "walk_in",
        "none",
    )
    assert (detail.marketing_consent, detail.consent) == (False, [])
    assert outbox() == [(events.CUSTOMER_CREATED, {"id": str(customer.id)})]


def test_the_full_card_keeps_every_value_and_the_phone_in_e164():
    detail = run(
        "customer.customer.create",
        CustomerIn(
            name="Ana",
            phone="600 111 222",
            email="ana@example.com",
            company_name="ACME",
            country="es",
            birthday="1990-05-04",
            lifecycle_stage="vip",
            source="whatsapp",
            preferred_channel="whatsapp",
            avatar="https://example.com/a.png",
        ),
    )
    assert (detail.phone, detail.company_name, detail.country, detail.birthday) == (
        "+34600111222",
        "ACME",
        "ES",
        "1990-05-04",
    )
    assert (
        detail.lifecycle_stage,
        detail.source,
        detail.preferred_channel,
        detail.avatar,
    ) == (
        "vip",
        "whatsapp",
        "whatsapp",
        "https://example.com/a.png",
    )


def test_a_phone_that_is_no_number_of_its_country_creates_nothing():
    with pytest.raises(InvalidPayload) as excinfo:
        run("customer.customer.create", CustomerIn(name="Ana", phone="600111"))
    status, code, fields = invalid(excinfo.value)
    assert (status, code, list(fields)) == (422, "customer.phone_invalid", ["phone"])
    assert fields["phone"].startswith("This is not a valid phone number of its country")
    assert not Customer.objects.exists() and outbox() == []


# customer.customer.update (CUSTOMER-F04)


def test_update_changes_only_what_was_sent_and_announces_it():
    ana = card("Ana", notes="keep me", email="old@example.com")
    detail = run(
        "customer.customer.update",
        CustomerPatchIn(id=ana.id, email="new@example.com", phone="+44 (0)7911 123456"),
    )
    assert (detail.email, detail.phone, detail.notes) == (
        "new@example.com",
        "+447911123456",
        "keep me",
    )
    assert outbox() == [(events.CUSTOMER_UPDATED, {"id": str(ana.id)})]


def test_update_by_the_customers_name_and_null_leaves_a_field_but_clears_a_date():
    ana = card("Ana", birthday="1990-01-01", city="Madrid")
    detail = run(
        "customer.customer.update",
        CustomerPatchIn(customer="ana", city=None, birthday=None, is_active=False),
    )
    assert (detail.city, detail.birthday, detail.is_active) == ("Madrid", None, False)
    ana.refresh_from_db()
    assert ana.birthday is None


def test_an_update_that_changes_nothing_announces_nothing():
    ana = card("Ana", phone="+34600111222")
    run(
        "customer.customer.update",
        CustomerPatchIn(id=ana.id, name="Ana", phone="600 111 222"),
    )
    assert outbox() == []


def test_an_update_with_a_bad_phone_changes_nothing():
    ana = card("Ana")
    with pytest.raises(InvalidPayload):
        run(
            "customer.customer.update",
            CustomerPatchIn(id=ana.id, name="Bea", phone="600 111 222 ext 12"),
        )
    ana.refresh_from_db()
    assert ana.name == "Ana" and outbox() == []


def test_a_card_that_is_gone_cannot_be_updated():
    gone = card("Gone", deleted_at=NOW)
    with pytest.raises(NotFound):
        run("customer.customer.update", CustomerPatchIn(id=gone.id, name="Back"))

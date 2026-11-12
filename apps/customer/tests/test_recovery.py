"""What Customers gives back from a separate copy of the business (hub#1257; BASE-F114, CUSTOMER-F01).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Customers answers it (``recoverable_from_copy`` on its
config) with its own read, by SQL over its model's names (``queries.cards_in_copy``): each live card of the copy with
what its create takes. Then, in the business, which of those it lacks (``queries.cards_not_in_business``): a card the
business has live, merged into another or with its personal data erased is not lacking, and neither is one it made
again (the same name, phone and email, the import's rule). One it deleted is still there (deleting keeps the card,
CUSTOMER-F07): it comes back the same, with all that hangs from it, by ``customer.customer.restore``
(``queries.cards_deleted_in_business``, hub#1306); only one the business no longer has is created, by
``customer.customer.create``.
"""

import uuid
from datetime import date, timedelta

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from apps.customer import queries
from apps.customer.models import Customer
from apps.customer.schemas import CustomerIn

pytestmark = pytest.mark.django_db


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


def test_the_copy_gives_each_live_card_with_what_its_create_takes():
    ana = Customer.objects.create(
        name="Ana López",
        email="ana@example.com",
        phone="+34600111222",
        tax_id="12345678Z",
        company_name="Ana SL",
        address="Calle Mayor 1",
        city="Madrid",
        postal_code="28001",
        country="ES",
        avatar="https://example.com/ana.png",
        birthday=date(1990, 1, 2),
        anniversary=date(2015, 6, 7),
        source="referral",
        lifecycle_stage="active",
        preferred_channel="email",
        notes="Prefers mornings",
    )
    now = timezone.now()
    Customer.objects.create(name="Gone", deleted_at=now, is_active=False)
    Customer.objects.create(name="Merged", deleted_at=now, merged_into=ana)
    Customer.objects.create(name="Deleted customer", deleted_at=now, erased_at=now)

    [read] = queries.cards_in_copy(direct())

    assert read.pop("id") == ana.pk
    assert CustomerIn.model_validate(read).model_dump() == {
        "name": "Ana López",
        "email": "ana@example.com",
        "phone": "+34600111222",
        "tax_id": "12345678Z",
        "company_name": "Ana SL",
        "address": "Calle Mayor 1",
        "city": "Madrid",
        "postal_code": "28001",
        "country": "ES",
        "avatar": "https://example.com/ana.png",
        "birthday": date(1990, 1, 2),
        "anniversary": date(2015, 6, 7),
        "source": "referral",
        "lifecycle_stage": "active",
        "preferred_channel": "email",
        "notes": "Prefers mornings",
    }


def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE customer_customer CASCADE")

    assert queries.cards_in_copy(direct()) == []


def a_card_of_the_copy(card: Customer | None = None, **fields) -> dict:
    """A card as the copy gives it: its id and the fields compared (``card``'s, or new ones)."""
    if card is not None:
        return {"id": card.pk, "name": card.name, "phone": card.phone, "email": card.email}
    return {"id": uuid.uuid7(), "name": "", "phone": "", "email": ""} | fields


def test_the_business_lacks_only_what_it_no_longer_has_nor_made_again():
    now = timezone.now()
    live = Customer.objects.create(name="Marta Ruiz", phone="+34600555666", email="marta@example.com")
    deleted = Customer.objects.create(name="Ana López", deleted_at=now, is_active=False)
    merged = Customer.objects.create(name="Luis Pérez", deleted_at=now, merged_into=live)
    erased = Customer.objects.create(name="Deleted customer", deleted_at=now, erased_at=now)
    absent = a_card_of_the_copy(name="Sara Gil", phone="+34600777888")
    # Deleted, and made again by hand since: the same name, phone and email as a live card, the case aside.
    again = a_card_of_the_copy(name="MARTA RUIZ", phone="+34600555666", email="Marta@Example.com")
    # Only the three together: two people may share a phone (CUSTOMER-F12).
    sharing = a_card_of_the_copy(name="Pablo Ruiz", phone="+34600555666", email="marta@example.com")
    cards = [a_card_of_the_copy(card) for card in (live, deleted, merged, erased)] + [absent, again, sharing]

    lacking = queries.cards_not_in_business(cards)

    assert [card["id"] for card in lacking] == [absent["id"], sharing["id"]]


def test_the_business_holds_deleted_only_the_card_deleted_from_its_card_and_not_made_again():
    now = timezone.now()
    live = Customer.objects.create(name="Marta Ruiz", phone="+34600555666", email="marta@example.com")
    deleted = Customer.objects.create(name="Ana López", phone="+34600111222", deleted_at=now, is_active=False)
    merged = Customer.objects.create(name="Luis Pérez", deleted_at=now, is_active=False, merged_into=live)
    erased = Customer.objects.create(name="Deleted customer", deleted_at=now, is_active=False, erased_at=now)
    # Deleted, and made again by hand since: a live card with the same name, phone and email, the case aside.
    twin = Customer.objects.create(name="Pablo Gil", phone="+34600777888", deleted_at=now, is_active=False)
    Customer.objects.create(name="PABLO GIL", phone="+34600777888")
    absent = a_card_of_the_copy(name="Sara Gil", phone="+34600999000")
    copy = [a_card_of_the_copy(card) for card in (live, deleted, merged, erased)]
    cards = [*copy, a_card_of_the_copy(twin), absent]

    held = queries.cards_deleted_in_business(cards)

    assert [card["id"] for card in held] == [deleted.pk]
    assert held[0] is cards[1]


def test_a_card_of_the_copy_is_in_the_business_live_in_the_one_it_was_merged_into_or_made_again():
    """hub#1284: what another app's recovery matches the card a record of the copy points at by (an appointment's
    customer): the rule ``cards_not_in_business`` tells a card is not lacking by, naming the business's card."""
    now = timezone.now()
    live = Customer.objects.create(name="Marta Ruiz", phone="+34600555666", email="marta@example.com")
    merged = Customer.objects.create(name="Luis Pérez", deleted_at=now, merged_into=live)
    # Merged into one merged since: it lives on in the last, CUSTOMER-F13.
    twice = Customer.objects.create(name="Luis P.", deleted_at=now, merged_into=merged)
    deleted = Customer.objects.create(name="Ana López", phone="+34600111222", deleted_at=now, is_active=False)
    erased = Customer.objects.create(name="Deleted customer", deleted_at=now, erased_at=now)
    # Gone, and made again by hand (or brought back already): the same name, phone and email, the case aside.
    again = a_card_of_the_copy(name="MARTA RUIZ", phone="+34600555666", email="Marta@Example.com")
    absent = a_card_of_the_copy(name="Sara Gil", phone="+34600777888")

    assert queries.card_in_business(a_card_of_the_copy(live)) == live.pk
    assert queries.card_in_business(a_card_of_the_copy(merged)) == live.pk
    assert queries.card_in_business(a_card_of_the_copy(twice)) == live.pk
    assert queries.card_in_business(again) == live.pk
    assert queries.card_in_business(a_card_of_the_copy(deleted)) is None
    assert queries.card_in_business(absent) is None
    # Erased (CUSTOMER-F16): never another card, not even one with the name, phone and email the copy still holds.
    assert queries.card_in_business({"id": erased.pk, "name": live.name, "phone": live.phone, "email": live.email}) is None


def test_of_two_cards_made_again_alike_the_business_card_is_the_oldest():
    """hub#1284: two live cards may share name, phone and email (CUSTOMER-F12 only warns): the record of the copy goes
    to the one made first, always the same, whatever order the database gives them in."""
    made_first = timezone.now() - timedelta(days=30)
    later = Customer.objects.create(name="Marta Ruiz", phone="+34600555666", email="marta@example.com")
    first = Customer.objects.create(name="Marta Ruiz", phone="+34600555666", email="marta@example.com")
    Customer.objects.filter(pk=first.pk).update(created_at=made_first)
    assert first.pk > later.pk

    again = a_card_of_the_copy(name="Marta Ruiz", phone="+34600555666", email="marta@example.com")

    assert queries.card_in_business(again) == first.pk


def test_the_app_declares_what_it_gives_back():
    [declared] = apps.get_app_config("customer").recoverable_from_copy()

    assert (declared.read, declared.missing, declared.create, declared.deleted, declared.restore) == (
        queries.cards_in_copy,
        queries.cards_not_in_business,
        "customer.customer.create",
        queries.cards_deleted_in_business,
        "customer.customer.restore",
    )
    assert str(declared.label) == "Customers"
    assert declared.reads_since == "0001_initial"

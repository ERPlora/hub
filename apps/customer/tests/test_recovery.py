"""What Customers gives back from a separate copy of the business (hub#1257; BASE-F114, CUSTOMER-F01).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Customers answers it (``recoverable_from_copy`` on its
config) with its own read, by SQL over its model's names (``queries.cards_in_copy``): each live card of the copy with
what its create takes. Then, in the business, which of those it lacks (``queries.cards_not_in_business``): a card the
business has live, merged into another or with its personal data erased is not lacking, and neither is one it made
again (the same name, phone and email, the import's rule). One it deleted is still there (deleting keeps the card,
CUSTOMER-F07): it comes back the same, with all that hangs from it and what the business deleted since (a group, a tag
or a custom field, hub#1356), by ``customer.customer.restore`` (``queries.cards_deleted_in_business``, hub#1306); only
one the business no longer has is created, by
``customer.customer.recover`` (hub#1285): as ``customer.customer.create`` makes it, with its groups, tags and custom
field values (``queries.recoverable_cards_in_copy``), each by the screen's own operation.

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid
from datetime import date, timedelta

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone
from live.operations import get as get_operation

from apps.customer import queries
from apps.customer.models import Customer, CustomerGroup, CustomerTag, CustomField, CustomFieldValue
from apps.customer.schemas import CustomerIn
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import ANA, CUSTOMERS, LUIS, Recoveries, fresh, gone, run, run_in



def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_the_app_declares_what_it_gives_back():
    [declared] = apps.get_app_config("customer").recoverable_from_copy()

    assert (declared.read, declared.missing, declared.create, declared.deleted, declared.restore) == (
        queries.recoverable_cards_in_copy,
        queries.cards_not_in_business,
        "customer.customer.recover",
        queries.cards_deleted_in_business,
        "customer.customer.restore",
    )
    assert str(declared.label) == "Customers"
    assert declared.reads_since == "0001_initial"


@pytest.mark.django_db
def test_the_copy_gives_each_card_with_its_groups_tags_and_custom_field_values_as_its_recovery_takes_them():
    """hub#1285: what hangs from a card comes back with it, by name: the business makes its own ids. A group or tag as
    the copy holds it, active or not (a card keeps an inactive one); only an active field's value (an inactive field
    shows on no card and takes no value, CUSTOMER-F29). Each with its id in the copy, which tells a deleted card's
    restore what the business still has (hub#1356)."""
    vip = CustomerGroup.objects.create(name="VIP", description="Best customers", color="warning", sort_order=2)
    old = CustomerGroup.objects.create(name="Old", is_active=False)
    regular = CustomerTag.objects.create(name="Regular", color="success")
    size = CustomField.objects.create(
        name="Size", field_type="select", options=["S", "M"], is_required=True, sort_order=1
    )
    pet = CustomField.objects.create(name="Pet", sort_order=2)
    retired = CustomField.objects.create(name="Retired", is_active=False)
    ana = Customer.objects.create(name="Ana López")
    ana.groups.add(vip, old)
    ana.tags.add(regular)
    for field, value in ((size, "M"), (pet, "Luna"), (retired, "Gone")):
        CustomFieldValue.objects.create(customer=ana, field=field, value=value)
    luis = Customer.objects.create(name="Luis Pérez")
    # A deleted card keeps what hangs from it (CUSTOMER-F07): the copy gives neither the card nor any of that.
    deleted = Customer.objects.create(name="Gone", deleted_at=timezone.now(), is_active=False)
    deleted.groups.add(vip)
    deleted.tags.add(regular)
    CustomFieldValue.objects.create(customer=deleted, field=pet, value="Rex")

    read = queries.recoverable_cards_in_copy(direct())

    # The cards as the copy gives them to the create, and what hangs from each.
    cards = queries.cards_in_copy(direct())
    assert [{key: card[key] for key in ("id", *queries.CARD_FIELDS)} for card in read] == cards
    assert [card["id"] for card in read] == [ana.pk, luis.pk]
    takes = get_operation("customer.customer.recover").input
    ana_read, luis_read = (takes.model_validate(card).model_dump() for card in read)
    assert ana_read["groups"] == [
        {"id": old.pk, "name": "Old", "description": "", "color": "primary", "sort_order": 0, "is_active": False},
        {
            "id": vip.pk,
            "name": "VIP",
            "description": "Best customers",
            "color": "warning",
            "sort_order": 2,
            "is_active": True,
        },
    ]
    assert ana_read["tags"] == [{"id": regular.pk, "name": "Regular", "color": "success", "is_active": True}]
    assert ana_read["field_values"] == [
        {
            "id": size.pk,
            "name": "Size",
            "field_type": "select",
            "options": ["S", "M"],
            "is_required": True,
            "sort_order": 1,
            "value": "M",
        },
        {
            "id": pet.pk,
            "name": "Pet",
            "field_type": "text",
            "options": [],
            "is_required": False,
            "sort_order": 2,
            "value": "Luna",
        },
    ]
    assert (luis_read["groups"], luis_read["tags"], luis_read["field_values"]) == ([], [], [])
    # A deleted card's restore takes the same of each card: its id and what hung from it.
    restores = get_operation("customer.customer.restore").input
    assert restores.model_validate(read[0]).model_dump(include={"groups", "tags", "field_values"}) == {
        key: ana_read[key] for key in ("groups", "tags", "field_values")
    }


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_no_card_to_recover():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE customer_customer CASCADE")

    assert queries.recoverable_cards_in_copy(direct()) == []


# ── End to end: the business's own database and its copy (hub#1285) ─────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


def what_hangs(hub, card) -> dict:
    """What hangs from ``card`` in ``hub``: its groups (name, id, active), tags (name, id, color) and custom field
    values (field name, field id, value)."""
    with use_hub(hub):
        customer = Customer.objects.get(pk=card)
        return {
            "groups": sorted(customer.groups.values_list("name", "id", "is_active")),
            "tags": sorted(customer.tags.values_list("name", "id", "color")),
            "values": sorted(customer.field_values.values_list("field__name", "field_id", "value")),
        }


def named(hub, model) -> list[tuple]:
    """Every group, tag or field of ``hub``: its name and whether it is active, by name."""
    with use_hub(hub):
        return sorted(model.objects.values_list("name", "is_active"))


#: The groups, tags and fields of ``a_business``, as its copy holds them (``all_named``).
AS_IN_THE_COPY = ([("Old", False), ("VIP", True)], [("Regular", True)], [("Pet", True), ("Size", True)])


def all_named(hub) -> tuple[list, list, list]:
    """Every group, tag and field of ``hub`` (``named``)."""
    return named(hub, CustomerGroup), named(hub, CustomerTag), named(hub, CustomField)


def the_new(hub, name: str):
    """The id of ``hub``'s live card named ``name``."""
    with use_hub(hub):
        return Customer.objects.live().get(name=name).pk


@pytest.mark.usefixtures("no_test_fallback")
class TestWhatHangsFromACardComesBack:
    """A card of the copy comes back with its groups, tags and custom field values (CUSTOMER-F06, CUSTOMER-F04,
    CUSTOMER-F29): the one the business deleted keeps its own (it is the same card), the one it no longer has gets them
    by Customers' own operations. A group, tag or field with the same name in the business is that one, never a second
    one; one the business no longer has is made again as the copy had it."""

    def a_business(self, recoveries, every_app_on):
        """Ana and Luis, each in the groups VIP and Old (deactivated since), with the tag Regular and the values Size M
        and Pet Luna; the ids of what hangs from them."""
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        made = {
            "vip": run_in(hub, "customer.group.create", name="VIP", color="warning").id,
            "old": run_in(hub, "customer.group.create", name="Old", sort_order=3).id,
            "regular": run_in(hub, "customer.tag.create", name="Regular", color="success").id,
            "size": run_in(hub, "customer.field.create", name="Size", field_type="select", options=["S", "M"]).id,
            "pet": run_in(hub, "customer.field.create", name="Pet").id,
        }
        for card in (ana, luis):
            run_in(hub, "customer.customer.set_groups", id=card, group_ids=[made["vip"], made["old"]])
            run_in(hub, "customer.customer.set_tags", id=card, tag_ids=[made["regular"]])
            values = [{"field_id": made["size"], "value": "M"}, {"field_id": made["pet"], "value": "Luna"}]
            run_in(hub, "customer.customer.update", id=card, field_values=values)
        run_in(hub, "customer.group.update", id=made["old"], is_active=False)
        return hub, ana, luis, made

    def luis_lost(self, recoveries, every_app_on):
        """``a_business`` and a copy of it, and then Luis's row gone altogether and the tag Regular deleted."""
        hub, _ana, luis, made = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone(hub, luis)
        run_in(hub, "customer.tag.delete", id=made["regular"])
        return hub, luis, made, copy

    def test_a_card_the_business_no_longer_has_comes_back_with_its_groups_tags_and_custom_fields(
        self, recoveries, every_app_on
    ):
        hub, ana, luis, made = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        # Lost since the copy: Luis's row altogether, and the group Old, the tag Regular and the field Pet.
        gone(hub, luis)
        run_in(hub, "customer.group.delete", id=made["old"])
        run_in(hub, "customer.tag.delete", id=made["regular"])
        run_in(hub, "customer.field.delete", id=made["pet"])
        asked = recoveries.ask(copy)

        assert run() == 1

        # Counted as one card made, not one a group, tag or field.
        assert fresh(asked).results == [CUSTOMERS | {"created": 1}]
        back = what_hangs(hub, the_new(hub, "Luis Pérez"))
        # VIP and Size, which the business still has, are those: never a second group or field of the same name.
        assert [group[:2] for group in back["groups"] if group[0] == "VIP"] == [("VIP", made["vip"])]
        assert [value[:2] for value in back["values"] if value[0] == "Size"] == [("Size", made["size"])]
        # Old, Regular and Pet, which it no longer has, made again as the copy had them, new ones by their operations.
        assert [(name, active) for name, _, active in back["groups"]] == [("Old", False), ("VIP", True)]
        assert [(name, color) for name, _, color in back["tags"]] == [("Regular", "success")]
        assert [(name, value) for name, _, value in back["values"]] == [("Pet", "Luna"), ("Size", "M")]
        assert made["old"] not in [group[1] for group in back["groups"]]
        assert all_named(hub) == AS_IN_THE_COPY
        with use_hub(hub):
            assert CustomerGroup.objects.get(name="Old").sort_order == 3
        # Ana, whom the business always had, stays as she is: what it took from her is not given back to her.
        kept = what_hangs(hub, ana)
        assert ([group[0] for group in kept["groups"]], kept["tags"]) == (["VIP"], [])
        assert [(name, value) for name, _, value in kept["values"]] == [("Size", "M")]

    def test_a_card_the_business_deleted_comes_back_the_same_with_what_hung_from_it(self, recoveries, every_app_on):
        hub, ana, _luis, made = self.a_business(recoveries, every_app_on)
        before = what_hangs(hub, ana)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        asked = recoveries.ask(copy)

        run()

        assert fresh(asked).results == [CUSTOMERS | {"restored": 1}]
        assert what_hangs(hub, ana) == before
        assert [group[1] for group in before["groups"]] == [made["old"], made["vip"]]
        assert all_named(hub) == AS_IN_THE_COPY

    def test_a_card_the_business_deleted_gets_back_the_group_tag_and_field_it_deleted_since(
        self, recoveries, every_app_on
    ):
        hub, ana, _luis, made = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        # Since the copy: Ana taken out of Old, which the business keeps; then her card deleted, and the group VIP,
        # the tag Regular and the field Pet deleted with what hung from them.
        run_in(hub, "customer.customer.set_groups", id=ana, group_ids=[made["vip"]])
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.group.delete", id=made["vip"])
        run_in(hub, "customer.tag.delete", id=made["regular"])
        run_in(hub, "customer.field.delete", id=made["pet"])
        asked = recoveries.ask(copy)

        assert run() == 1

        # The same card back, counted once, as restored.
        assert fresh(asked).results == [CUSTOMERS | {"restored": 1}]
        back = what_hangs(hub, ana)
        # In VIP again, with Regular and Pet, each made again as the copy had it; Size, which the business kept, is
        # that one; Old, which it keeps too, stays without her, as the business left it.
        assert [(name, active) for name, _, active in back["groups"]] == [("VIP", True)]
        assert made["vip"] not in [group[1] for group in back["groups"]]
        assert [(name, color) for name, _, color in back["tags"]] == [("Regular", "success")]
        assert [(name, value) for name, _, value in back["values"]] == [("Pet", "Luna"), ("Size", "M")]
        assert [value[1] for value in back["values"] if value[0] == "Size"] == [made["size"]]
        assert all_named(hub) == AS_IN_THE_COPY
        with use_hub(hub):
            assert CustomerGroup.objects.get(name="VIP").color == "warning"

    def test_two_deleted_cards_of_a_group_deleted_since_come_back_in_one_group_made_again(
        self, recoveries, every_app_on
    ):
        hub, ana, luis, made = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        for card in (ana, luis):
            run_in(hub, "customer.customer.delete", id=card)
        run_in(hub, "customer.group.delete", id=made["vip"])
        asked = recoveries.ask(copy)

        run()

        assert fresh(asked).results == [CUSTOMERS | {"restored": 2}]
        assert named(hub, CustomerGroup) == [("Old", False), ("VIP", True)]
        with use_hub(hub):
            vip = CustomerGroup.objects.get(name="VIP")
            assert sorted(Customer.objects.live().filter(groups=vip).values_list("name", flat=True)) == [
                "Ana López",
                "Luis Pérez",
            ]

    def test_asked_again_nothing_is_made_twice(self, recoveries, every_app_on):
        hub, _luis, _made, copy = self.luis_lost(recoveries, every_app_on)
        recoveries.ask(copy)
        run()
        again = recoveries.ask(copy)

        run()

        assert fresh(again).results == [CUSTOMERS]
        assert named(hub, CustomerTag) == [("Regular", True)]
        with use_hub(hub):
            assert Customer.objects.live().filter(name="Luis Pérez").count() == 1

    def test_a_value_its_field_no_longer_takes_does_not_keep_the_card_out_and_recoveries_notes_it_with_why(
        self, recoveries, every_app_on
    ):
        hub, luis, made, copy = self.luis_lost(recoveries, every_app_on)
        # Size no longer offers M: the card's screen would not save it either.
        run_in(hub, "customer.field.update", id=made["size"], options=["S", "L"])
        asked = recoveries.ask(copy)

        run()

        # Luis made again, counted once as made and once as noted: the note says, by his id in the copy, which field
        # he came back without and why.
        [result] = fresh(asked).results
        [note] = result.pop("notes")
        assert result == CUSTOMERS | {"created": 1, "noted": 1}
        assert note["id"] == str(luis)
        assert note["note"].startswith("customer.field_invalid_option: ") and '"Size"' in note["note"]
        back = what_hangs(hub, the_new(hub, "Luis Pérez"))
        assert [(name, value) for name, _, value in back["values"]] == [("Pet", "Luna")]
        assert [(name, color) for name, _, color in back["tags"]] == [("Regular", "success")]

    def test_a_field_the_business_deactivated_or_made_required_since_does_not_keep_the_card_out(
        self, recoveries, every_app_on
    ):
        hub, luis, made, copy = self.luis_lost(recoveries, every_app_on)
        # Pet deactivated: it shows on no card, so its value does not come back, and no second Pet is made.
        run_in(hub, "customer.field.update", id=made["pet"], is_active=False)
        # A field required since: a card is made without it, as the till makes one (CUSTOMER-F01).
        run_in(hub, "customer.field.create", name="Allergies", is_required=True)
        asked = recoveries.ask(copy)

        run()

        # Recoveries says Luis came back without his Pet, and why; the required field without a value is no note.
        [result] = fresh(asked).results
        [note] = result.pop("notes")
        assert result == CUSTOMERS | {"created": 1, "noted": 1}
        assert (note["id"], note["note"].startswith("customer.field_inactive: ")) == (str(luis), True)
        back = what_hangs(hub, the_new(hub, "Luis Pérez"))
        assert [(name, value) for name, _, value in back["values"]] == [("Size", "M")]
        assert named(hub, CustomField) == [("Allergies", True), ("Pet", False), ("Size", True)]

    def test_a_card_the_business_deleted_comes_back_without_a_value_the_field_it_made_again_no_longer_takes_noted(
        self, recoveries, every_app_on
    ):
        hub, ana, _luis, made = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        # Since the copy: Ana's card deleted, then Size deleted with its values and made again by hand without M.
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.field.delete", id=made["size"])
        run_in(hub, "customer.field.create", name="Size", field_type="select", options=["S", "L"])
        asked = recoveries.ask(copy)

        run()

        # The same card back, counted as restored and as noted, not kept deleted for one value.
        [result] = fresh(asked).results
        [note] = result.pop("notes")
        assert result == CUSTOMERS | {"restored": 1, "noted": 1}
        assert note["id"] == str(ana)
        assert note["note"].startswith("customer.field_invalid_option: ") and '"Size"' in note["note"]
        back = what_hangs(hub, ana)
        assert [(name, value) for name, _, value in back["values"]] == [("Pet", "Luna")]
        with use_hub(hub):
            assert Customer.objects.live().filter(pk=ana).exists()

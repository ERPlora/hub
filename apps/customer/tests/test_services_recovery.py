"""Bringing back a deleted card and making one again from a separate copy (CUSTOMER-F33)."""

import uuid

import pytest
from django.utils import translation
from live.errors import NotFound, PermissionDenied

from apps.customer import events
from apps.customer.models import (
    Activity,
    CustomField,
    CustomFieldValue,
    Customer,
    CustomerGroup,
    CustomerTag,
    OrderLink,
    Purchase,
)
from apps.customer.schemas.activity import NoteIn
from apps.customer.schemas.consent import ConsentGrantIn
from apps.customer.schemas.fields import CustomerRefIn as RefIn
from apps.customer.schemas.recovery import CustomerRecoverIn, CustomerRestoreIn
from apps.customer.services.recovery import FIELD_INACTIVE_LEFT, FIELD_OPTION_LEFT, FIELD_TYPE_LEFT

from .conftest import HUB_DB, NOW, card, clear_outbox, outbox, run, system

pytestmark = HUB_DB


# customer.customer.restore (CUSTOMER-F33; BASE-F114, the recovery from a separate copy, hub#1306)


def test_restore_brings_the_same_card_back_with_all_that_hangs_from_it_and_announces_it():
    ana = card("Ana", email="ana@example.com", phone="+34600111222", total_purchases=1, total_spent=500)
    vip = CustomerGroup.objects.create(name="VIP")
    ana.groups.add(vip)
    Purchase.objects.create(customer=ana, sale_id=uuid.uuid7(), amount=500)
    OrderLink.objects.create(order_id=uuid.uuid7(), customer=ana)
    run("customer.note.add", NoteIn(customer_id=ana.id, content="Prefers mornings"))
    run(
        "customer.consent.grant",
        ConsentGrantIn(customer_id=ana.id, channel="sms", notice_text="I want offers.", notice_version="v1"),
    )
    run("customer.customer.delete", RefIn(id=ana.id))
    clear_outbox()

    back = system("customer.customer.restore", CustomerRestoreIn(id=ana.id))

    assert (back.id, back.left_out) == (ana.id, [])
    ana.refresh_from_db()
    assert (ana.deleted_at, ana.is_active) == (None, True)
    assert Customer.objects.live().filter(pk=ana.pk).exists()
    assert (ana.purchases.count(), ana.orders.count(), ana.consents.count(), list(ana.groups.all())) == (1, 1, 1, [vip])
    assert ana.activity.filter(kind=Activity.Kind.NOTE_ADDED, text="Prefers mornings").exists()
    assert (ana.total_purchases, ana.total_spent, ana.phone) == (1, 500, "+34600111222")
    assert outbox() == [(events.CUSTOMER_RESTORED, {"id": str(ana.id)})]


def test_restoring_a_live_card_answers_well_changes_nothing_and_announces_again():
    ana = card("Ana")
    before = Customer.objects.get(pk=ana.pk).updated_at

    assert system("customer.customer.restore", CustomerRestoreIn(id=ana.id)).id == ana.id

    assert Customer.objects.get(pk=ana.pk).updated_at == before
    assert outbox() == [(events.CUSTOMER_RESTORED, {"id": str(ana.id)})]


@pytest.mark.parametrize("gone", ["merged", "erased", "unknown"])
def test_a_card_merged_into_another_erased_or_unknown_never_comes_back(gone):
    survivor = card("Marta")
    lost = {
        "merged": lambda: card("Luis", deleted_at=NOW, is_active=False, merged_into=survivor).id,
        "erased": lambda: card("Deleted customer", deleted_at=NOW, is_active=False, erased_at=NOW).id,
        "unknown": uuid.uuid7,
    }[gone]()

    with pytest.raises(NotFound) as refused:
        system("customer.customer.restore", CustomerRestoreIn(id=lost))

    assert refused.value.code == "customer.customer_unavailable"
    assert list(Customer.objects.live().values_list("name", flat=True)) == ["Marta"]
    assert outbox() == []


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"])
def test_only_the_system_restores_a_card(role):
    ana = card("Ana", deleted_at=NOW, is_active=False)

    with pytest.raises(PermissionDenied):
        run("customer.customer.restore", CustomerRestoreIn(id=ana.id), role)

    assert Customer.objects.get(pk=ana.pk).deleted_at == NOW


def restored_with(ana: Customer, **hanging):
    """``customer.customer.restore`` of ``ana`` as the recovery gives it: with what hung from her card in a separate
    copy, each with its id there."""
    return system("customer.customer.restore", CustomerRestoreIn.model_validate({"id": ana.id} | hanging))


def test_restore_gives_back_what_the_business_deleted_since_and_leaves_what_it_has_as_it_is():
    """hub#1356: a group, tag or field the business still has (by its id in the copy) is its own, the card in it or
    not; one it deleted since is made again as the copy had it, by its screen's operation, and the card goes back in
    it, as a card made again from the copy (hub#1285)."""
    regulars = CustomerGroup.objects.create(name="Regulars")
    # Kept, Known and Size the business still has: it took Ana out of Kept and of Known and cleared her Size before
    # deleting her.
    kept = CustomerGroup.objects.create(name="Kept")
    known = CustomerTag.objects.create(name="Known")
    size = CustomField.objects.create(name="Size", field_type="select", options=["S", "M"])
    ana = card("Ana", deleted_at=NOW, is_active=False)
    ana.groups.add(regulars)
    clear_outbox()

    restored_with(
        ana,
        groups=[
            {"id": regulars.id, "name": "Regulars"},
            {"id": kept.id, "name": "Kept"},
            {"id": uuid.uuid7(), "name": "VIP", "color": "warning", "sort_order": 2},
            {"id": uuid.uuid7(), "name": "Old", "is_active": False},
        ],
        tags=[{"id": known.id, "name": "Known"}, {"id": uuid.uuid7(), "name": "Regular", "color": "success"}],
        field_values=[
            {"id": size.id, "name": "Size", "field_type": "select", "options": ["S", "M"], "value": "M"},
            {"id": uuid.uuid7(), "name": "Pet", "sort_order": 2, "value": "Luna"},
        ],
    )

    ana.refresh_from_db()
    assert (ana.deleted_at, ana.is_active) == (None, True)
    assert sorted(ana.groups.values_list("name", "color", "sort_order", "is_active")) == [
        ("Old", "primary", 0, False),
        ("Regulars", "primary", 0, True),
        ("VIP", "warning", 2, True),
    ]
    assert list(ana.tags.values_list("name", "color", "is_active")) == [("Regular", "success", True)]
    pet = CustomField.objects.get(name="Pet")
    assert (pet.sort_order, list(ana.field_values.values_list("field_id", "value"))) == (2, [(pet.id, "Luna")])
    assert (CustomerGroup.objects.count(), CustomerTag.objects.count(), CustomField.objects.count()) == (4, 2, 2)
    names = [name for name, _ in outbox()]
    assert names[0] == events.CUSTOMER_RESTORED
    assert sorted(names[1:]) == sorted(
        [
            events.GROUP_CREATED,
            events.GROUP_CREATED,
            events.GROUP_UPDATED,
            events.CUSTOMER_GROUPS_CHANGED,
            events.TAG_CREATED,
            events.CUSTOMER_TAGS_CHANGED,
            events.FIELD_CREATED,
        ]
    )


def test_restore_puts_the_card_in_what_the_business_made_again_by_name_and_keeps_its_own_value():
    """A group, tag or field the business deleted and made again by hand is that one (its name, the case aside), never a
    second one; a value the card holds already in it stays, and a field made again and deactivated takes none: the
    card comes back without it, and says so. Its own value kept is nothing left out."""
    vip = CustomerGroup.objects.create(name="vip")
    regular = CustomerTag.objects.create(name="REGULAR")
    pet = CustomField.objects.create(name="Pet")
    CustomField.objects.create(name="Size", is_active=False)
    ana = card("Ana", deleted_at=NOW, is_active=False)
    CustomFieldValue.objects.create(customer=ana, field=pet, value="Max")

    back = restored_with(
        ana,
        groups=[{"id": uuid.uuid7(), "name": "VIP"}],
        tags=[{"id": uuid.uuid7(), "name": "Regular"}],
        field_values=[{"id": uuid.uuid7(), "name": "Pet", "value": "Luna"}, {"id": uuid.uuid7(), "name": "Size", "value": "M"}],
    )

    ana.refresh_from_db()
    assert (list(ana.groups.all()), list(ana.tags.all())) == ([vip], [regular])
    assert list(ana.field_values.values_list("field_id", "value")) == [(pet.id, "Max")]
    assert (CustomerGroup.objects.count(), CustomerTag.objects.count(), CustomField.objects.count()) == (1, 1, 2)
    assert [one.code for one in back.left_out] == ["customer.field_inactive"]
    assert '"Size"' in back.left_out[0].message


def test_restore_brings_the_card_back_without_a_value_its_field_no_longer_takes_and_says_why():
    """A field the business made again by hand with other options does not keep the card deleted: it comes back with
    all else that hung from it, without that value, and the output says which field and why."""
    CustomField.objects.create(name="Size", field_type="select", options=["S", "L"])
    ana = card("Ana", deleted_at=NOW, is_active=False)

    back = restored_with(
        ana,
        tags=[{"id": uuid.uuid7(), "name": "Regular"}],
        field_values=[
            {"id": uuid.uuid7(), "name": "Size", "field_type": "select", "options": ["S", "M"], "value": "M"},
            {"id": uuid.uuid7(), "name": "Pet", "value": "Luna"},
        ],
    )

    ana.refresh_from_db()
    assert (ana.deleted_at, ana.is_active) == (None, True)
    assert list(ana.tags.values_list("name", flat=True)) == ["Regular"]
    assert list(ana.field_values.values_list("field__name", "value")) == [("Pet", "Luna")]
    assert list(CustomField.objects.filter(name="Size").values_list("options", flat=True)) == [["S", "L"]]
    assert [one.code for one in back.left_out] == ["customer.field_invalid_option"]
    assert '"Size"' in back.left_out[0].message


# customer.customer.recover (BASE-F114, the recovery from a separate copy, hub#1285)


def a_card_of_the_copy(**fields) -> CustomerRecoverIn:
    """A card of a separate copy as its recovery takes it: what the create takes and what hung from it there."""
    return CustomerRecoverIn.model_validate({"name": "Luis Pérez", "phone": "+34600333444"} | fields)


def test_recover_makes_the_card_with_its_groups_tags_and_values_by_the_screens_own_operations():
    vip = CustomerGroup.objects.create(name="VIP")
    vegan = CustomerTag.objects.create(name="Vegan")
    size = CustomField.objects.create(name="Size", field_type="select", options=["S", "M"])
    clear_outbox()

    made = system(
        "customer.customer.recover",
        a_card_of_the_copy(
            groups=[{"name": "vip"}, {"name": "Old", "color": "danger", "sort_order": 4, "is_active": False}],
            tags=[{"name": "VEGAN"}, {"name": "Regular", "color": "success"}, {"name": "Winter", "is_active": False}],
            field_values=[
                {"name": "SIZE", "field_type": "select", "options": ["S", "M"], "value": "M"},
                {"name": "Pet", "field_type": "text", "sort_order": 2, "value": "Luna"},
            ],
        ),
    )

    luis = Customer.objects.get(pk=made.id)
    assert (luis.name, luis.phone) == ("Luis Pérez", "+34600333444")
    # VIP and Size are the business's own, by name: never a second one.
    old = CustomerGroup.objects.get(name="Old")
    assert set(luis.groups.all()) == {vip, old}
    assert (old.color, old.sort_order, old.is_active) == ("danger", 4, False)
    assert sorted(luis.tags.values_list("name", "color", "is_active")) == [
        ("Regular", "success", True),
        ("Vegan", "primary", True),
        ("Winter", "primary", False),
    ]
    assert vegan in luis.tags.all()
    pet = CustomField.objects.get(name="Pet")
    assert (pet.field_type, pet.sort_order, pet.is_active) == ("text", 2, True)
    assert sorted(luis.field_values.values_list("field_id", "value")) == sorted([(size.id, "M"), (pet.id, "Luna")])
    assert (CustomerGroup.objects.count(), CustomerTag.objects.count(), CustomField.objects.count()) == (2, 3, 2)
    # Each by its own operation, with its own event: the card's create, the group, tag and field it made again, and
    # the card's groups and tags set as its screen sets them.
    names = [name for name, _ in outbox()]
    assert names[0] == events.CUSTOMER_CREATED
    assert sorted(names[1:]) == sorted(
        [
            events.GROUP_CREATED,
            events.GROUP_UPDATED,
            events.CUSTOMER_GROUPS_CHANGED,
            events.TAG_CREATED,
            events.TAG_CREATED,
            events.TAG_UPDATED,
            events.CUSTOMER_TAGS_CHANGED,
            events.FIELD_CREATED,
        ]
    )


def test_recover_reuses_the_active_one_of_a_name_over_one_deactivated():
    CustomerGroup.objects.create(name="VIP", is_active=False)
    live = CustomerGroup.objects.create(name="vip")

    made = system("customer.customer.recover", a_card_of_the_copy(groups=[{"name": "VIP"}]))

    assert list(Customer.objects.get(pk=made.id).groups.all()) == [live]
    assert CustomerGroup.objects.count() == 2


def test_recover_reuses_the_oldest_of_a_name_when_the_business_has_none_active():
    """Deactivating a group frees its name, so the business may hold several deactivated ones of a name:
    the card goes to the one made first, always the same, whatever order the database gives them in."""
    first = CustomerGroup.objects.create(name="VIP", is_active=False)
    CustomerGroup.objects.create(name="vip", is_active=False)
    oldest = CustomerTag.objects.create(name="Regular", is_active=False)
    CustomerTag.objects.create(name="regular", is_active=False)

    made = system("customer.customer.recover", a_card_of_the_copy(groups=[{"name": "VIP"}], tags=[{"name": "Regular"}]))

    luis = Customer.objects.get(pk=made.id)
    assert (list(luis.groups.all()), list(luis.tags.all())) == ([first], [oldest])
    assert (CustomerGroup.objects.count(), CustomerTag.objects.count()) == (2, 2)


def test_recover_without_anything_hanging_makes_the_card_as_its_create_does():
    clear_outbox()

    made = system("customer.customer.recover", a_card_of_the_copy())

    luis = Customer.objects.get(pk=made.id)
    assert (luis.groups.count(), luis.tags.count(), luis.field_values.count()) == (0, 0, 0)
    assert outbox() == [(events.CUSTOMER_CREATED, {"id": str(luis.id)})]
    assert made.left_out == []


def test_recover_makes_the_card_without_a_value_its_field_no_longer_takes_and_says_why():
    """A value no longer one of its field's options, or no longer of its field's type, does not keep the card out: it
    is made with all else, without those values, and the output says each field and why, in the copy's order."""
    CustomField.objects.create(name="Size", field_type="select", options=["S", "L"])
    CustomField.objects.create(name="Shoe", field_type="number")
    clear_outbox()

    made = system(
        "customer.customer.recover",
        a_card_of_the_copy(
            tags=[{"name": "Regular"}],
            field_values=[
                {"name": "Size", "field_type": "select", "options": ["S", "M"], "value": "M"},
                {"name": "Pet", "value": "Luna"},
                {"name": "Shoe", "value": "forty"},
            ],
        ),
    )

    luis = Customer.objects.get(pk=made.id)
    assert list(luis.tags.values_list("name", flat=True)) == ["Regular"]
    assert list(luis.field_values.values_list("field__name", "value")) == [("Pet", "Luna")]
    assert [one.code for one in made.left_out] == ["customer.field_invalid_option", "customer.field_invalid_number"]
    assert [one.message for one in made.left_out] == [
        FIELD_OPTION_LEFT % {"field": "Size"},
        FIELD_TYPE_LEFT % {"field": "Shoe"},
    ]


def test_recover_leaves_out_a_value_of_a_field_deactivated_says_why_and_never_asks_a_required_one():
    CustomField.objects.create(name="Pet", is_active=False)
    nickname = CustomField.objects.create(name="Nickname")
    allergies = CustomField.objects.create(name="Allergies", is_required=True)

    made = system(
        "customer.customer.recover",
        a_card_of_the_copy(field_values=[{"name": "Pet", "value": "Luna"}, {"name": "Nickname", "value": "Lu"}]),
    )

    luis = Customer.objects.get(pk=made.id)
    assert list(luis.field_values.values_list("field_id", "value")) == [(nickname.id, "Lu")]
    assert CustomField.objects.filter(name="Pet").count() == 1
    assert not CustomFieldValue.objects.filter(field=allergies).exists()
    # The required field it has no value of is nothing it came back without: the till makes a card so too.
    assert [one.code for one in made.left_out] == ["customer.field_inactive"]
    assert '"Pet"' in made.left_out[0].message


def test_what_a_card_came_back_without_is_said_in_the_language_it_is_made_in():
    CustomField.objects.create(name="Pet", is_active=False)

    with translation.override("es"):
        made = system("customer.customer.recover", a_card_of_the_copy(field_values=[{"name": "Pet", "value": "Luna"}]))
        [said] = made.left_out
        spanish = FIELD_INACTIVE_LEFT % {"field": "Pet"}

    assert said.message == spanish
    assert said.message != FIELD_INACTIVE_LEFT % {"field": "Pet"}


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"])
def test_only_the_system_recovers_a_card_from_a_copy(role):
    with pytest.raises(PermissionDenied):
        run("customer.customer.recover", a_card_of_the_copy(), role)

    assert Customer.objects.count() == 0

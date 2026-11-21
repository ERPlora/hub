"""MODIFIER-F11, the server's part: an option declares the allergens it adds to the dish, of the fourteen that must be
declared, by its own create and change, through the API and the assistant alike. Every read of an option carries them:
its detail and the list, the groups the till asks for a product and the valuation of what was chosen (MODIFIER-F12
reads them there). The list, the type and the refusal are the platform's (``base.allergens``), the ones Inventory's
products use."""

import json
import uuid

import pytest
from django.db import connections
from live.assistant.running import invalid_arguments
from live.models import OutboxEvent
from live.operations import get as get_operation

from apps.flow.tests.test_api import get, post
from apps.inventory.tests.test_allergens import NOT_ONE_OF_THE_FOURTEEN
from apps.inventory.tests.test_assistant_card_records import fields_of
from apps.modifier import events
from apps.modifier.models import ModifierOption
from apps.modifier.schemas import OptionIn, OptionPatchIn
from base.models import Membership
from base.tenancy.context import current_alias, use_hub
from base.tests.test_assistant_asks import assert_offered_with_room, comparable, probe_phrases

from .conftest import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, catalog_of, ctx_for, make_product, run
from .test_services import received

pytestmark = HUB_DB
#: The fixture taken from the conftest: the assistant's catalogue of a person of business A.
__all__ = ["catalog_of"]

#: What the WORKBOOK says a person asks the assistant for (MODIFIER-F11), in their words: none of the tool's asks.
MARK_MILK = "marca leche en el queso de Extras"


@pytest.fixture
def extras():
    return run("modifier.group.create", {"name": "Extras"})


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", role="hub_admin"))
    return client


def option(name="Cheese", **fields):
    return run("modifier.option.create", {"group": "Extras", "name": name, **fields})


def update(option_id, **fields):
    return run("modifier.option.update", {"id": str(option_id), **fields})


def updated() -> list[str]:
    return list(OutboxEvent.objects.filter(name=events.OPTION_UPDATED).values_list("name", flat=True))


# The option keeps them


def test_an_option_has_no_allergens_until_it_declares_them(extras):
    cheese = option()
    assert cheese.allergens == []
    assert ModifierOption.objects.get(pk=cheese.id).allergens == []


def test_an_option_written_by_code_that_does_not_know_the_allergens_has_none(extras):
    """Expand/contract: while a deploy rolls, a process still on the previous code inserts options without the column;
    the database gives it its default instead of refusing the row."""
    option_id = uuid.uuid7()
    with connections[current_alias()].cursor() as cursor:
        cursor.execute(
            "INSERT INTO modifier_modifieroption (id, group_id, name, kitchen_name, price_delta, tax_category_id,"
            " is_default, sort_order, created_at, updated_at, created_by, updated_by) VALUES (%s, %s, 'Old', '', 0,"
            " NULL, false, 0, now(), now(), '', '')",
            [option_id, extras.id],
        )
    assert ModifierOption.objects.get(pk=option_id).allergens == []


def test_the_create_keeps_each_allergen_once_in_the_order_of_the_list(extras):
    cheese = option(allergens=["milk", "gluten", "milk"])
    assert cheese.allergens == ["gluten", "milk"]
    assert ModifierOption.objects.get(pk=cheese.id).allergens == ["gluten", "milk"]


def test_a_change_sets_them_and_modifiers_tells_of_it_as_of_any_other_change(extras):
    cheese = option()
    changed = update(cheese.id, allergens=["mustard", "milk"])
    assert changed.allergens == ["milk", "mustard"]
    assert ModifierOption.objects.get(pk=cheese.id).allergens == ["milk", "mustard"]
    assert updated() == [events.OPTION_UPDATED]


def test_a_change_that_does_not_send_them_leaves_them_and_an_empty_list_clears_them(extras):
    cheese = option(allergens=["milk"])
    assert update(cheese.id, price_delta=150).allergens == ["milk"]
    assert update(cheese.id, allergens=[]).allergens == []
    assert ModifierOption.objects.get(pk=cheese.id).allergens == []


def test_sending_the_same_allergens_again_changes_nothing_and_tells_nothing(extras):
    cheese = option(allergens=["gluten", "milk"])
    update(cheese.id, allergens=["milk", "gluten"])
    assert updated() == []


@pytest.mark.parametrize("schema", [OptionIn, OptionPatchIn])
def test_the_option_takes_the_platforms_closed_list_of_allergens(schema):
    """The same type and the same check as a product's: the fourteen codes, each once and in the order of the list."""
    field = schema.model_json_schema()["properties"]["allergens"]
    items = field.get("items") or next(one for one in field["anyOf"] if one.get("type") == "array")["items"]
    assert items["enum"] == ["gluten", "crustaceans", "egg", "fish", "peanut", "soy", "milk", "tree_nuts", "celery",
                             "mustard", "sesame", "sulphites", "lupin", "molluscs"]


# Refused off the list, by the API and the assistant alike


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_api_refuses_an_allergen_off_the_list_on_its_field_and_creates_nothing(extras, admin_client, language):
    response = admin_client.post(
        "/api/modifier/options",
        json.dumps({"group": "Extras", "name": "Cheese", "allergens": ["milk", "nuts"]}),
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_ACCEPT_LANGUAGE=language,
    )
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (422, "invalid_payload")
    assert error["fields"] == {"allergens": NOT_ONE_OF_THE_FOURTEEN[language]}
    assert not ModifierOption.objects.exists()


def test_the_api_refuses_a_change_off_the_list_and_keeps_the_allergens_it_had(extras, admin_client):
    cheese = option(allergens=["milk"])
    response = post(admin_client, "/modifier/options/update", {"id": str(cheese.id), "allergens": ["cheese"]})
    assert (response.status_code, set(response.json()["error"]["fields"])) == (422, {"allergens"})
    assert ModifierOption.objects.get(pk=cheese.id).allergens == ["milk"]


def test_the_api_saves_them_and_reads_them_back(extras, admin_client):
    created = post(admin_client, "/modifier/options", {"group": "Extras", "name": "Cheese", "allergens": ["milk"]})
    read = get(admin_client, "/modifier/options/detail", id=created.json()["id"])
    assert (created.status_code, created.json()["allergens"]) == (201, ["milk"])
    assert (read.status_code, read.json()["allergens"]) == (200, ["milk"])


def test_an_employee_reads_them_but_does_not_change_them(extras, client, make_user):
    cheese = option(allergens=["milk"])
    client.force_login(make_user("ana", role="hub_employee"))
    read = get(client, "/modifier/options/detail", id=str(cheese.id))
    changed = post(client, "/modifier/options/update", {"id": str(cheese.id), "allergens": []})
    assert (read.status_code, read.json()["allergens"]) == (200, ["milk"])
    assert (changed.status_code, changed.json()["error"]["code"]) == (403, "permission_denied")
    assert ModifierOption.objects.get(pk=cheese.id).allergens == ["milk"]


def test_the_assistant_hears_the_refusal_before_any_card_is_drawn(extras):
    cheese = option()
    refused = invalid_arguments(get_operation("modifier.option.update"), {"id": str(cheese.id), "allergens": ["cheese"]})
    assert (refused.outcome, refused.code) == ("error", "invalid_payload")
    fields = json.loads(refused.content)["error"]["fields"]
    assert (set(fields), NOT_ONE_OF_THE_FOURTEEN["en"] in fields["allergens"]) == ({"allergens"}, True)


def test_the_assistants_card_says_the_allergens_by_their_names_in_spanish(extras):
    cheese = option("Queso")
    fields = fields_of("modifier.option.update", {"id": str(cheese.id), "allergens": ["milk", "gluten"]}, "es")
    assert (fields["allergens"]["label"], fields["allergens"]["value"]) == ("Alérgenos", ["Leche", "Gluten"])


def test_the_assistants_card_of_a_new_option_says_them_too(extras):
    fields = fields_of("modifier.option.create", {"group": "Extras", "name": "Queso", "allergens": ["milk"]}, "es")
    assert (fields["allergens"]["label"], fields["allergens"]["value"]) == ("Alérgenos", ["Leche"])


def test_asking_the_assistant_to_mark_an_allergen_on_an_option_offers_its_change(catalog_of):
    assert comparable(MARK_MILK) not in probe_phrases()
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), "modifier.option.update", MARK_MILK)


# Every read of an option carries them


def test_the_option_and_the_list_carry_its_allergens(extras):
    cheese = option(allergens=["milk"])
    option("Rare")
    assert run("modifier.option.get", {"id": str(cheese.id)}, role="hub_employee").allergens == ["milk"]
    page = run("modifier.option.list", {"group": "Extras"}, role="hub_employee")
    assert {row.name: row.allergens for row in page.rows} == {"Cheese": ["milk"], "Rare": []}


def test_the_groups_the_till_asks_for_a_product_carry_each_options_allergens(extras):
    burger = make_product()
    run("modifier.link.attach", {"group": "Extras", "product_id": str(burger.id)})
    option(allergens=["milk"])
    option("Mustard sauce", allergens=["mustard"])
    option("No onion")
    target = run("modifier.group.for_target", {"product_id": str(burger.id)}, role="hub_employee")
    assert {one.name: one.allergens for one in target.groups[0].options} == {
        "Cheese": ["milk"], "Mustard sauce": ["mustard"], "No onion": []
    }


# Each business its own


@HUB_DB_COMMITTED
def test_allergens_declared_in_business_b_tell_b_only_and_stay_in_b(listen, hub_b):
    with use_hub(hub_b):
        ctx = ctx_for("hub_admin", B)
        run("modifier.group.create", {"name": "Extras"}, ctx=ctx)
        cheese = run("modifier.option.create", {"group": "Extras", "name": "Cheese"}, ctx=ctx)
        on_a, on_b = listen(A), listen(B)
        run("modifier.option.update", {"id": str(cheese.id), "allergens": ["milk"]}, ctx=ctx)
        assert ModifierOption.objects.get(pk=cheese.id).allergens == ["milk"]

    assert received(on_b, stop_after=1) == [{"events": [events.OPTION_UPDATED]}]
    assert received(on_a, timeout=0.3) == []
    assert not ModifierOption.objects.exists()

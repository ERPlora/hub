"""«Ponle foto al café con leche» (INVENTORY-F30 step 5; C.8 of the round 2026-10-30): the assistant puts a product's
photo from the shared library with the tools every operation is by construction (``ai=``).

Asked in Spanish, the turn offers ``inventory.product.suggest_image`` and ``inventory.product.set_image`` (never the
upload: a file is picked on the screen). The suggestion for «Café con leche» brings the library's coffee with milk first,
titled in the business's language; it sets nothing. The card that confirms the write names the image by its title,
never by its reference.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext
from live.operations import get

from apps.tax.models import TaxCategory
from base import assistant
from base.models import Hub, Membership
from base.permissions import permissions_for
from base.tests.test_image_catalog import image_library  # noqa: F401 - the library fixture

from .conftest import A

pytestmark = pytest.mark.django_db

LATTE = "catalog:hospitality/cafe_con_leche"
ASKED = "ponle foto al café con leche"


@pytest.fixture
def owner() -> OperationContext:
    user = get_user_model().objects.create_user(username="olga", password="pw")
    Membership.objects.create(user=user, host=A.key, role=Membership.Role.OWNER)
    return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language="es")


@pytest.fixture
def latte(owner, db):
    TaxCategory.objects.get_or_create(key="restaurant.drink", defaults={"name": "Drinks"})
    Hub.objects.filter(slug=A.key).update(language="es")
    op = get("inventory.product.create")
    return op(owner, op.input(name="Café con leche", sku="CAF-02", price=180, tax_category_key="restaurant.drink"))


def test_asked_for_a_photo_the_turn_offers_the_suggestion_and_the_set_but_never_the_upload(owner):
    tools = assistant.catalog(owner)

    offered = [op.name for op in assistant.relevant(tools, [ASKED], "es")]

    assert "inventory.product.suggest_image" in offered
    assert "inventory.product.set_image" in offered
    assert "inventory.product.upload_image" not in tools


def test_the_suggestion_for_cafe_con_leche_brings_the_coffee_with_milk_first(owner, latte, image_library):  # noqa: F811
    outcome = assistant.run_tool(owner, get("inventory.product.suggest_image"), json.dumps({"product": "café con leche"}))

    assert outcome.outcome == "ok", outcome.content
    rows = json.loads(outcome.content)["rows"]
    assert (rows[0]["reference"], rows[0]["title"]) == (LATTE, "Café con leche")
    assert get("inventory.product.get")(owner, get("inventory.product.get").input(id=latte.id)).image == ""


def test_the_card_names_the_image_by_its_title_never_by_its_reference(owner, latte, image_library):  # noqa: F811
    card = assistant.card(get("inventory.product.set_image"), {"product": "Café con leche", "image": LATTE}, "es", owner)

    [image] = [field for field in card["fields"] if field["name"] == "image"]
    assert (image["label"], image["value"]) == ("Imagen", "Café con leche")
    assert card["risk"] == "normal"


def test_a_photo_the_card_cannot_name_is_left_out_of_it(owner, latte, image_library):  # noqa: F811
    card = assistant.card(
        get("inventory.product.set_image"), {"product": "Café con leche", "image": "catalog:hospitality/churros"}, "es", owner
    )

    assert [field["name"] for field in card["fields"]] == ["product"]

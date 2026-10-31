"""A menu's image (COMBO-F14; round 2026-10-30): ``Combo.image``, as a product's (INVENTORY-F30, F31) through
``base.images``.

The market sells a set menu on the till as one more item, with its picture: Odoo POS (a combo is a product, with its
image), Lightspeed (a combo has its own image), Toast (a combo is a menu item, which takes an image), Shopify POS (a
bundle is a product), Loyverse (a composite item has its picture), Square and SumUp (items with photos); the old
library already had ``menu_dia``, ``menu_infantil``, ``menu_hamburguesa`` and ``menu_kebab``. So a menu shows an image
of the shared library or a photo of its own, or its initials: ``combo.combo.set_image`` (the library or none),
``combo.combo.upload_image`` (a photo, kept as a 512 × 512 WebP), ``combo.combo.suggest_image`` (the library's best for
its name, never set). Withdrawing the menu (COMBO-F04) deletes its photo once saved.
"""

import base64
import io
import json
import re

import pytest
from django.apps import apps as django_apps
from django.db.migrations.operations import AddField
from live.errors import InvalidPayload, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from PIL import Image as PILImage

from apps.combo import events
from apps.combo.models import Combo
from apps.combo.schemas import (
    ComboDetailOut,
    ComboImageIn,
    ComboImageSuggestOut,
    ComboImageUploadIn,
)
from base.models import Hub
from base.storage import hub_prefix
from base.tests.test_image_catalog import IMAGES, write_library
from base.tests.test_images import hub_files  # noqa: F401 - the store fixture

from .conftest import ctx_for, make_combo, make_group, make_option, make_product, run

pytestmark = pytest.mark.django_db

FOLDER = "combo/combos/"
MENU = "catalog:hospitality/menu_dia"
#: apps/combo/tests/test_api.py's ROUTES takes these.
IMAGE_ROUTES = {
    ("POST", "/combo/combos/image", "combo.combo.set_image"),
    ("POST", "/combo/combos/image/upload", "combo.combo.upload_image"),
    ("GET", "/combo/combos/image/suggest", "combo.combo.suggest_image"),
}


@pytest.fixture
def library(settings, tmp_path):
    menu = {
        "name": "menu_dia",
        "folder": "hospitality",
        "title": {"en": "Menu of the day", "es": "Menú del día"},
        "tags": {"en": ["set menu", "lunch"], "es": ["menú", "comida"]},
    }
    settings.CATALOG_DIR = str(write_library(tmp_path / "img", [*IMAGES, menu]))


def photo() -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (640, 480), "teal").save(buffer, "JPEG")
    return buffer.getvalue()


def upload(combo_id, raw=None, role="hub_admin"):
    data = {"id": str(combo_id), "data_base64": base64.b64encode(raw or photo()).decode()}
    return run("combo.combo.upload_image", data, ctx_for(role))


def key(reference: str) -> str:
    return f"{hub_prefix(Hub.objects.get(slug='a').id)}/{reference.removeprefix('file:')}"


def test_a_menu_is_born_without_an_image_and_its_photos_are_the_hubs_sessions_only():
    combo = make_combo()

    detail = run("combo.combo.get", {"id": str(combo.id)})

    assert (detail.image, detail.image_url) == ("", "")
    assert django_apps.get_app_config("combo").members_media == [FOLDER]


def test_the_column_is_added_with_a_database_default():
    migration = __import__("apps.combo.migrations.0002_combo_image", fromlist=["Migration"]).Migration
    [operation] = migration.operations

    assert isinstance(operation, AddField) and (operation.model_name, operation.name) == ("combo", "image")
    assert (operation.field.default, operation.field.db_default) == ("", "")


def test_the_three_operations_and_who_may_run_them():
    set_op, upload_op, suggest_op = (get(f"combo.combo.{name}") for name in ("set_image", "upload_image", "suggest_image"))

    assert (set_op.kind, set_op.permission, set_op.input, set_op.output) == ("command", "combo.manage", ComboImageIn, ComboDetailOut)
    assert set_op.ai["risk"] == "normal" and "catalog:" in set_op.ai["description"]
    assert (upload_op.permission, upload_op.input) == ("combo.manage", ComboImageUploadIn)
    assert upload_op.ai["description"].startswith("Not an assistant tool")
    assert (suggest_op.kind, suggest_op.permission, suggest_op.output) == ("query", "combo.view", ComboImageSuggestOut)
    assert ComboImageIn.model_json_schema()["properties"]["image"]["refers"]["read"] == "base.catalog_image.get"


def test_an_image_of_the_library_is_set_by_its_name_and_the_screens_hear_of_it(library):
    combo = make_combo()

    changed = run("combo.combo.set_image", {"combo": "menu of the day", "image": MENU})

    assert (changed.image, changed.image_url) == (MENU, "/p/catalog/hospitality/menu_dia.webp")
    assert [row.payload["id"] for row in OutboxEvent.objects.filter(name=events.COMBO_UPDATED)] == [str(combo.id)]


def test_what_is_no_image_of_the_library_is_refused(library):
    combo = make_combo()

    with pytest.raises(InvalidPayload) as refused:
        run("combo.combo.set_image", {"id": str(combo.id), "image": f"file:{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp"})

    assert refused.value.code == "base.image_unknown"
    assert Combo.objects.get().image == ""


def test_an_employee_may_not_change_it(library):
    combo = make_combo()

    with pytest.raises(PermissionDenied):
        run("combo.combo.set_image", {"id": str(combo.id), "image": MENU}, ctx_for("hub_employee"))


def test_a_photo_takes_the_place_of_the_last_one_and_withdrawing_the_menu_deletes_it(
    hub_files, django_capture_on_commit_callbacks  # noqa: F811
):
    combo = make_combo()
    first = upload(combo.id).image

    with django_capture_on_commit_callbacks(execute=True):
        second = upload(combo.id).image
    assert re.fullmatch(rf"file:{FOLDER}[0-9a-f]{{32}}\.webp", second)
    assert not hub_files.exists(key(first)) and hub_files.exists(key(second))

    with django_capture_on_commit_callbacks(execute=True):
        run("combo.combo.delete", {"id": str(combo.id)})
    assert not hub_files.exists(key(second))


def test_the_list_and_the_tills_menus_say_the_image(library):
    combo = make_combo()
    make_option(make_group(combo, min_choices=1, max_choices=1), make_product())
    run("combo.combo.set_image", {"id": str(combo.id), "image": MENU})

    [listed] = run("combo.combo.list", {}).rows
    [for_sale] = run("combo.combo.for_sale", {}).rows

    assert (listed.image, listed.image_url) == (MENU, "/p/catalog/hospitality/menu_dia.webp")
    assert (for_sale.image, for_sale.image_url) == (MENU, "/p/catalog/hospitality/menu_dia.webp")


def test_it_suggests_the_librarys_images_for_its_name_and_sets_none(library):
    combo = make_combo("Menú del día")

    found = run("combo.combo.suggest_image", {"id": str(combo.id)}, ctx_for("hub_employee"))

    assert (found.query, found.rows[0].reference) == ("Menú del día", MENU)
    assert Combo.objects.get().image == ""
    assert found.combo_id == combo.id


def test_the_routes(client, make_user, library):
    combo = make_combo()
    client.force_login(make_user("boss", host="a", role="hub_admin"))

    response = client.post(
        "/api/combo/combos/image",
        json.dumps({"id": str(combo.id), "image": MENU}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
    )

    assert response.status_code == 200, response.content
    assert response.json()["image_url"] == "/p/catalog/hospitality/menu_dia.webp"


def test_asked_for_a_menus_photo_the_assistants_turn_offers_the_suggestion_and_the_set():
    from base import assistant

    tools = assistant.catalog(ctx_for("hub_admin"))
    offered = [op.name for op in assistant.relevant(tools, ["ponle foto al menú del día"], "es")]

    assert {"combo.combo.suggest_image", "combo.combo.set_image"} <= set(offered)
    assert "combo.combo.upload_image" not in tools

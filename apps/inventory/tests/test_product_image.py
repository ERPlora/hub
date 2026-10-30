"""A product's image (round 2026-10-30, «blueprints con imágenes»; the WORKBOOK's «duda 6»): ``Product.image``.

A product shows an image of the shared library (``catalog:<folder>/<name>``, ``base.image_catalog``) or a photo of its
own (``file:inventory/products/<uuid7 hex>.webp`` under its hub's prefix, ``base.images``), or none: the till shows its
initials. ``inventory.product.set_image`` sets one of the library (or none), ``inventory.product.upload_image`` keeps a
photo (a JPG, PNG or WebP of 2 MB at most, kept as a 512 × 512 WebP) and ``inventory.product.suggest_image`` proposes
the library's best images for the product's name, never setting one. Every read of a product says its ``image`` and
the ``image_url`` the screens show; the photos are served to the hub's sessions only (``members_media``).
"""

import base64
import io
import json
import os
import re
import uuid
from dataclasses import replace

import pytest
from django.apps import apps as django_apps
from django.db.migrations.operations import AddField
from django.utils import translation
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from PIL import Image as PILImage

from apps.inventory import events
from apps.inventory.models import Product
from apps.inventory.schemas import (
    ForSaleListIn,
    ProductImageIn,
    ProductImageSuggestIn,
    ProductImageSuggestOut,
    ProductImageUploadIn,
    ProductIn,
    ProductListIn,
    ProductOut,
    ProductRefIn,
)
from apps.tax.models import TaxCategory
from base.models import Hub
from base.storage import hub_prefix
from base.tests.test_image_catalog import image_library, webp  # noqa: F401 - the library fixture
from base.tests.test_images import hub_files  # noqa: F401 - the store fixture

from .conftest import ctx_for

pytestmark = pytest.mark.django_db

TAX = "test.general"
FOLDER = "inventory/products/"
LATTE = "catalog:hospitality/cafe_con_leche"
#: The route set of the three operations (apps/inventory/tests/test_api.py's ROUTES takes them).
IMAGE_ROUTES = {
    ("POST", "/inventory/products/image", "inventory.product.set_image"),
    ("POST", "/inventory/products/image/upload", "inventory.product.upload_image"),
    ("GET", "/inventory/products/image/suggest", "inventory.product.suggest_image"),
}


@pytest.fixture(autouse=True)
def general(db):
    return TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})[0]


def run(name, data, role="hub_admin", language="en"):
    return get(name)(replace(ctx_for(role), language=language), data)


def product(name="Café con leche", sku="CAF-02") -> ProductOut:
    return run("inventory.product.create", ProductIn(name=name, sku=sku, price=180, tax_category_key=TAX))


def set_image(image, product_id=None, said=None, role="hub_admin"):
    return run("inventory.product.set_image", ProductImageIn(id=product_id, product=said, image=image), role)


def upload(raw: bytes, product_id=None, said=None, role="hub_admin", language="en"):
    data = ProductImageUploadIn(id=product_id, product=said, data_base64=base64.b64encode(raw).decode())
    return run("inventory.product.upload_image", data, role, language)


def suggest(product_id=None, said=None, **params):
    return run("inventory.product.suggest_image", ProductImageSuggestIn(id=product_id, product=said, **params))


def photo(fmt="PNG", size=(800, 600)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", size, "orange").save(buffer, fmt)
    return buffer.getvalue()


def updates():
    return [row.payload["id"] for row in OutboxEvent.objects.filter(name=events.PRODUCT_UPDATED).order_by("created_at", "id")]


def clear_outbox():
    OutboxEvent.objects.all().delete()


def hub_a() -> uuid.UUID:
    return Hub.objects.get(slug="a").id


def key(reference: str) -> str:
    return f"{hub_prefix(hub_a())}/{reference.removeprefix('file:')}"


# ── The model and its migration ────────────────────────────────────────────────────────────────────────────────


def test_a_product_is_born_without_an_image():
    created = product()

    assert (created.image, created.image_url) == ("", "")
    assert Product.objects.get().image == ""


def test_the_column_is_added_with_a_database_default_so_the_previous_code_still_inserts():
    migration = __import__("apps.inventory.migrations.0005_product_image", fromlist=["Migration"]).Migration
    [operation] = migration.operations

    assert isinstance(operation, AddField) and operation.name == "image"
    assert (operation.field.default, operation.field.db_default, operation.field.max_length) == ("", "", 200)


def test_its_photos_are_served_to_the_hubs_sessions_only():
    assert django_apps.get_app_config("inventory").members_media == [FOLDER]


# ── Declarations ───────────────────────────────────────────────────────────────────────────────────────────────


def test_set_and_upload_are_commands_of_whoever_changes_products_and_upload_is_no_tool():
    image_set, image_upload = get("inventory.product.set_image"), get("inventory.product.upload_image")

    assert (image_set.kind, image_set.permission, image_set.input, image_set.output, image_set.expose_api) == (
        "command", "inventory.change_product", ProductImageIn, ProductOut, True,
    )
    assert image_set.ai["risk"] == "normal" and "catalog:" in image_set.ai["description"]
    assert (image_upload.kind, image_upload.permission, image_upload.input, image_upload.output) == (
        "command", "inventory.change_product", ProductImageUploadIn, ProductOut,
    )
    assert image_upload.ai["description"].startswith("Not an assistant tool")


def test_suggest_is_a_read_for_whoever_sees_products_and_a_tool_of_the_assistant():
    op = get("inventory.product.suggest_image")

    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query", "inventory.view_product", ProductImageSuggestIn, ProductImageSuggestOut, True,
    )
    assert "image" in op.ai["description"] and "never" in op.ai["description"]


def test_the_image_a_write_sets_is_named_on_the_assistants_card_by_its_title():
    marked = ProductImageIn.model_json_schema()["properties"]["image"]["refers"]

    assert marked == {"read": "base.catalog_image.get", "by": "reference", "name": ["title"]}


# ── inventory.product.set_image ────────────────────────────────────────────────────────────────────────────────


def test_an_image_of_the_library_is_set_and_every_screen_hears_of_it(image_library):  # noqa: F811
    created = product()
    clear_outbox()

    changed = set_image(LATTE, created.id)

    assert (changed.image, changed.image_url) == (LATTE, "/p/catalog/hospitality/cafe_con_leche.webp")
    assert Product.objects.get().image == LATTE
    assert Product.objects.get().updated_by == "tester"
    assert updates() == [str(created.id)]


def test_a_product_is_named_by_its_sku_or_its_name_as_said_aloud(image_library):  # noqa: F811
    created = product()

    assert set_image(LATTE, said="caf-02").id == created.id
    assert set_image("catalog:hospitality/latte", said="café con leche").image == "catalog:hospitality/latte"


def test_setting_the_image_it_already_shows_records_nothing(image_library):  # noqa: F811
    created = product()
    set_image(LATTE, created.id)
    clear_outbox()

    set_image(LATTE, created.id)

    assert updates() == []


def test_an_empty_image_takes_it_away(image_library):  # noqa: F811
    created = product()
    set_image(LATTE, created.id)
    clear_outbox()

    changed = set_image("", created.id)

    assert (changed.image, changed.image_url) == ("", "")
    assert updates() == [str(created.id)]


@pytest.mark.parametrize(
    "image",
    [
        "catalog:hospitality/churros",
        "https://cdn.example.com/cafe.webp",
        "/p/catalog/hospitality/cafe_con_leche.webp",
        f"file:{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp",
        "file:service/services/0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp",
    ],
)
def test_what_is_no_image_of_the_library_or_of_this_hub_is_refused_and_nothing_changes(image_library, hub_files, image):  # noqa: F811
    created = product()
    clear_outbox()

    with pytest.raises(InvalidPayload) as refused:
        set_image(image, created.id)

    assert (refused.value.code, set(refused.value.fields)) == ("base.image_unknown", {"image"})
    assert Product.objects.get().image == ""
    assert updates() == []


def test_a_photo_of_its_own_is_never_set_by_hand_not_even_its_own(image_library, hub_files):  # noqa: F811
    first, second = product(), product("Cortado", "CAF-03")
    own = upload(photo(), first.id).image

    for target in (first.id, second.id):
        with pytest.raises(InvalidPayload) as refused:
            set_image(own, target)
        assert refused.value.message == "Choose an image of the library or upload a photo."

    assert (Product.objects.get(pk=first.id).image, Product.objects.get(pk=second.id).image) == (own, "")


def test_a_photo_of_its_own_replaced_by_an_image_of_the_library_is_deleted_once_saved(
    image_library, hub_files, django_capture_on_commit_callbacks  # noqa: F811
):
    created = product()
    own = upload(photo(), created.id).image

    with django_capture_on_commit_callbacks(execute=True):
        set_image(LATTE, created.id)

    assert not hub_files.exists(key(own))


def test_an_employee_may_not_change_the_image(image_library):  # noqa: F811
    created = product()

    with pytest.raises(PermissionDenied):
        set_image(LATTE, created.id, role="hub_employee")


def test_without_the_library_an_image_of_it_cannot_be_set(settings, tmp_path):
    created = product()
    settings.CATALOG_DIR = str(tmp_path / "nowhere")

    with pytest.raises(OperationError) as refused:
        set_image(LATTE, created.id)

    assert (refused.value.status, refused.value.code) == (503, "base.image_library_unavailable")


def test_an_unknown_product_is_not_found(image_library):  # noqa: F811
    with pytest.raises(NotFound):
        set_image(LATTE, uuid.uuid7())


# ── inventory.product.upload_image ─────────────────────────────────────────────────────────────────────────────


def test_a_photo_is_kept_as_a_webp_of_512_under_the_hubs_products_folder_and_shown(hub_files):  # noqa: F811
    created = product()
    clear_outbox()

    changed = upload(photo("JPEG", (1200, 800)), created.id)

    match = re.fullmatch(rf"file:{FOLDER}([0-9a-f]{{32}})\.webp", changed.image)
    assert match and uuid.UUID(match.group(1)).version == 7
    assert changed.image_url == f"/p/media/{hub_a().hex}/{changed.image.removeprefix('file:')}"
    kept = PILImage.open(hub_files.open(key(changed.image)))
    assert (kept.format, kept.size) == ("WEBP", (512, 512))
    assert updates() == [str(created.id)]


def test_a_new_photo_takes_the_place_of_the_last_one_which_is_deleted_once_saved(
    hub_files, django_capture_on_commit_callbacks  # noqa: F811
):
    created = product()
    first = upload(photo(), created.id).image

    with django_capture_on_commit_callbacks(execute=True):
        second = upload(photo("PNG", (300, 300)), created.id).image

    assert second != first
    assert hub_files.exists(key(second)) and not hub_files.exists(key(first))


def test_a_photo_past_2_mb_is_refused_and_nothing_is_kept(hub_files):  # noqa: F811
    created = product()

    with pytest.raises(InvalidPayload) as refused:
        upload(b"\0" * (2 * 1024 * 1024 + 1), created.id)

    assert (refused.value.code, set(refused.value.fields)) == ("base.photo_too_big", {"data_base64"})
    assert Product.objects.get().image == ""


def test_a_photo_somewhat_past_2_mb_is_told_it_weighs_too_much_not_a_length_of_text(hub_files):  # noqa: F811
    created = product()

    with pytest.raises(InvalidPayload) as refused:
        upload(b"\0" * (2 * 1024 * 1024 + 50_000), created.id)

    assert refused.value.code == "base.photo_too_big"


def test_a_file_that_is_no_photo_is_refused_in_the_persons_language(hub_files):  # noqa: F811
    created = product()

    with pytest.raises(InvalidPayload) as refused:
        upload(b"%PDF-1.7 not a photo", created.id, language="es")

    assert refused.value.code == "base.photo_invalid"
    assert refused.value.message == "Ese archivo no es una foto. Sube una imagen JPG, PNG o WebP."


def test_a_photo_past_the_plans_space_is_refused_and_the_product_keeps_its_image(hub_files):  # noqa: F811
    created = product()
    Hub.objects.filter(slug="a").update(state={"plan": {"max_storage_bytes": 10}})

    with pytest.raises(Conflict) as refused:
        upload(photo(), created.id)

    assert refused.value.code == "base.file_no_space"
    assert Product.objects.get().image == ""


def test_deleting_the_product_deletes_its_photo_once_saved(hub_files, django_capture_on_commit_callbacks):  # noqa: F811
    created = product()
    own = upload(photo(), created.id).image

    with django_capture_on_commit_callbacks(execute=True):
        run("inventory.product.delete", ProductRefIn(id=created.id))

    assert not hub_files.exists(key(own))
    assert Product.objects.get().image == ""


def test_a_store_that_does_not_answer_leaves_the_product_with_the_photo_it_had(hub_files, monkeypatch):  # noqa: F811
    created = product()
    first = upload(photo(), created.id).image
    monkeypatch.setattr(hub_files, "save", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("down")))

    with pytest.raises(OperationError) as refused:
        upload(photo(), created.id)

    assert (refused.value.status, refused.value.code) == (503, "base.photo_not_saved")
    assert Product.objects.get().image == first


def test_a_photo_for_a_product_that_is_not_there_keeps_nothing(hub_files):  # noqa: F811
    with pytest.raises(NotFound):
        upload(photo(), uuid.uuid7())

    from base import files

    assert files.used_bytes(hub_files, hub_a()) == 0


def test_an_employee_may_not_upload_a_photo(hub_files):  # noqa: F811
    created = product()

    with pytest.raises(PermissionDenied):
        upload(photo(), created.id, role="hub_employee")


# ── inventory.product.suggest_image ────────────────────────────────────────────────────────────────────────────


def test_it_suggests_the_librarys_images_for_the_products_name_the_best_first_and_sets_none(image_library):  # noqa: F811
    created = product("Café con leche")
    clear_outbox()

    found = suggest(created.id)

    assert found.query == "Café con leche"
    assert [row.reference for row in found.rows][:2] == [LATTE, "catalog:hospitality/latte"]
    assert found.rows[0].title == "White coffee"
    assert Product.objects.get().image == ""
    assert OutboxEvent.objects.count() == 0


def test_the_suggestions_are_titled_in_the_businesss_language_for_an_employee_too(image_library):  # noqa: F811
    created = product("White coffee")
    Hub.objects.filter(slug="a").update(language="es")

    found = run("inventory.product.suggest_image", ProductImageSuggestIn(id=created.id), "hub_employee", language="en")

    assert (found.rows[0].reference, found.rows[0].title) == (LATTE, "Café con leche")


def test_it_suggests_at_most_the_number_asked(image_library):  # noqa: F811
    created = product("Café con leche")

    assert len(suggest(created.id, limit=1).rows) == 1


def test_a_name_the_library_has_nothing_for_gets_no_suggestion(image_library):  # noqa: F811
    created = product("Tornillo de 5 mm", "TOR-5")

    assert suggest(created.id).rows == []


# ── Every read says it ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_list_the_detail_and_the_tills_catalog_say_the_image_and_its_url(image_library, hub_files):  # noqa: F811
    latte, own = product(), product("Cortado", "CAF-03")
    set_image(LATTE, latte.id)
    reference = upload(photo(), own.id).image
    url = f"/p/media/{hub_a().hex}/{reference.removeprefix('file:')}"

    listed = {row.sku: (row.image, row.image_url) for row in run("inventory.product.list", ProductListIn()).rows}
    detail = run("inventory.product.get", ProductRefIn(id=own.id))
    for_sale = {row.sku: (row.image, row.image_url) for row in run("inventory.product.list_for_sale", ForSaleListIn()).rows}

    expected = {"CAF-02": (LATTE, "/p/catalog/hospitality/cafe_con_leche.webp"), "CAF-03": (reference, url)}
    assert listed == expected
    assert for_sale == expected
    assert (detail.image, detail.image_url) == (reference, url)


def test_a_product_without_image_reads_without_asking_the_hub(monkeypatch):
    product()
    from base import images

    monkeypatch.setattr(images, "hub_id", lambda scope: pytest.fail("the hub was read for no photo"))

    assert run("inventory.product.list", ProductListIn()).rows[0].image_url == ""


# ── Over HTTP ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


def post(client, path, data):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST="a.localhost")


def test_a_photo_of_nearly_2_mb_goes_through_the_route(admin_client, hub_files):  # noqa: F811
    created = product()
    # Noise does not compress: about 1.9 MB of PNG, 2.6 MB of base64, more than Django takes in any other body.
    raw = io.BytesIO()
    PILImage.frombytes("RGB", (800, 800), os.urandom(800 * 800 * 3)).save(raw, "PNG")
    assert 1_800_000 < len(raw.getvalue()) <= 2 * 1024 * 1024

    response = post(
        admin_client,
        "/inventory/products/image/upload",
        {"id": str(created.id), "data_base64": base64.b64encode(raw.getvalue()).decode()},
    )

    assert response.status_code == 200, response.content[:300]
    assert response.json()["image"].startswith(f"file:{FOLDER}")


def test_set_and_suggest_over_http(admin_client, image_library):  # noqa: F811
    created = product()

    response = post(admin_client, "/inventory/products/image", {"id": str(created.id), "image": LATTE})
    found = admin_client.get(
        "/api/inventory/products/image/suggest", {"id": str(created.id)}, HTTP_HOST="a.localhost"
    )

    assert response.status_code == 200, response.content
    assert response.json()["image_url"] == "/p/catalog/hospitality/cafe_con_leche.webp"
    assert found.status_code == 200, found.content
    assert found.json()["rows"][0]["reference"] == LATTE


def test_a_session_of_the_hub_sees_a_products_photo_and_a_visitor_does_not(admin_client, client, hub_files):  # noqa: F811
    created = product()
    url = upload(photo(), created.id).image_url

    seen = admin_client.get(url, HTTP_HOST="a.localhost:8000")
    assert seen.status_code == 200
    assert seen["Content-Type"] == "image/webp"
    admin_client.logout()
    assert admin_client.get(url, HTTP_HOST="a.localhost:8000").status_code == 404


def test_the_image_is_said_in_english_and_spanish():
    with translation.override("es"):
        assert str(Product._meta.get_field("image").verbose_name) == "imagen"

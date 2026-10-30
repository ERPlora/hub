"""A service's image (SERVICE-F34, SERVICE-F35; round 2026-10-30): ``Service.image``, as a product's (INVENTORY-F30,
F31) through ``base.images``.

A service shows an image of the shared library (``catalog:<folder>/<name>``; for the hair salon, ``beauty_hair/`` and
``beauty_body/``) or a photo of its own (``file:service/services/<uuid7 hex>.webp`` under its hub's prefix), or none: the
till's tile shows its initials. ``service.service.set_image`` sets one of the library (or none; a ``file:`` only its
upload writes), ``service.service.upload_image`` keeps a photo, ``service.service.suggest_image`` proposes the library's
best images for its name. Replacing a photo deletes the last one once saved; archiving the service keeps it, in case it
is restored (SERVICE-F05).
"""

import base64
import io
import json
import re
import uuid
from dataclasses import replace

import pytest
from django.apps import apps as django_apps
from django.db.migrations.operations import AddField
from live.errors import InvalidPayload, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from PIL import Image as PILImage

from apps.service import events
from apps.service.models import Service
from apps.service.schemas import (
    ServiceForSaleIn,
    ServiceImageIn,
    ServiceImageSuggestIn,
    ServiceImageSuggestOut,
    ServiceImageUploadIn,
    ServiceIn,
    ServiceListIn,
    ServiceOut,
    ServiceRefIn,
)
from apps.tax.models import TaxCategory
from base.models import Hub
from base.storage import hub_prefix
from base.tests.test_image_catalog import image_library, webp  # noqa: F401 - the library fixture
from base.tests.test_images import hub_files  # noqa: F401 - the store fixture

from .conftest import ctx_for

pytestmark = pytest.mark.django_db

TAX = "service.generic"
FOLDER = "service/services/"
CUT = "catalog:beauty_hair/corte_senora"
#: apps/service/tests/test_api.py's ROUTES takes these.
IMAGE_ROUTES = {
    ("POST", "/service/services/image", "service.service.set_image"),
    ("POST", "/service/services/image/upload", "service.service.upload_image"),
    ("GET", "/service/services/image/suggest", "service.service.suggest_image"),
}


@pytest.fixture(autouse=True)
def generic(db):
    return TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "Services"})[0]


def run(name, data, role="hub_admin", language="en"):
    return get(name)(replace(ctx_for(role), language=language), data)


def service(name="Women's cut") -> ServiceOut:
    return run("service.service.create", ServiceIn(name=name, tax_category_key=TAX, price=2500))


def set_image(image, service_id, role="hub_admin"):
    return run("service.service.set_image", ServiceImageIn(id=service_id, image=image), role)


def upload(raw: bytes, service_id, role="hub_admin"):
    return run(
        "service.service.upload_image",
        ServiceImageUploadIn(id=service_id, data_base64=base64.b64encode(raw).decode()),
        role,
    )


def photo(size=(700, 500)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", size, "purple").save(buffer, "PNG")
    return buffer.getvalue()


def updates():
    return [row.payload["id"] for row in OutboxEvent.objects.filter(name=events.SERVICE_UPDATED)]


def key(reference: str) -> str:
    return f"{hub_prefix(Hub.objects.get(slug='a').id)}/{reference.removeprefix('file:')}"


# ── The model, its migration and its folder ────────────────────────────────────────────────────────────────────


def test_a_service_is_born_without_an_image():
    created = service()

    assert (created.image, created.image_url) == ("", "")


def test_the_column_is_added_with_a_database_default_so_the_previous_code_still_inserts():
    migration = __import__("apps.service.migrations.0003_service_image", fromlist=["Migration"]).Migration
    [operation] = migration.operations

    assert isinstance(operation, AddField) and (operation.model_name, operation.name) == ("service", "image")
    assert (operation.field.default, operation.field.db_default, operation.field.max_length) == ("", "", 200)


def test_its_photos_are_served_to_the_hubs_sessions_only():
    assert django_apps.get_app_config("service").members_media == [FOLDER]


# ── Declarations ───────────────────────────────────────────────────────────────────────────────────────────────


def test_the_three_operations_and_who_may_run_them():
    set_op, upload_op, suggest_op = (get(f"service.service.{name}") for name in ("set_image", "upload_image", "suggest_image"))

    assert (set_op.kind, set_op.permission, set_op.input, set_op.output, set_op.expose_api) == (
        "command", "service.change_service", ServiceImageIn, ServiceOut, True,
    )
    assert set_op.ai["risk"] == "normal" and "catalog:" in set_op.ai["description"]
    assert (upload_op.kind, upload_op.permission, upload_op.input, upload_op.output) == (
        "command", "service.change_service", ServiceImageUploadIn, ServiceOut,
    )
    assert upload_op.ai["description"].startswith("Not an assistant tool")
    assert (suggest_op.kind, suggest_op.permission, suggest_op.input, suggest_op.output) == (
        "query", "service.view_service", ServiceImageSuggestIn, ServiceImageSuggestOut,
    )
    assert "never" in suggest_op.ai["description"]


def test_the_image_a_write_sets_is_named_on_the_assistants_card_by_its_title():
    marked = ServiceImageIn.model_json_schema()["properties"]["image"]["refers"]

    assert marked == {"read": "base.catalog_image.get", "by": "reference", "name": ["title"]}


# ── service.service.set_image ──────────────────────────────────────────────────────────────────────────────────


def test_an_image_of_the_library_is_set_and_the_till_hears_of_it(image_library):  # noqa: F811
    created = service()
    OutboxEvent.objects.all().delete()

    changed = set_image(CUT, created.id)

    assert (changed.image, changed.image_url) == (CUT, "/p/catalog/beauty_hair/corte_senora.webp")
    assert updates() == [str(created.id)]


def test_by_its_name_as_said_aloud(image_library):  # noqa: F811
    created = service()

    changed = run("service.service.set_image", ServiceImageIn(service="women's cut", image=CUT))

    assert changed.id == created.id


def test_the_same_image_again_records_nothing_and_empty_takes_it_away(image_library):  # noqa: F811
    created = service()
    set_image(CUT, created.id)
    OutboxEvent.objects.all().delete()

    set_image(CUT, created.id)
    assert updates() == []
    assert set_image("", created.id).image_url == ""
    assert updates() == [str(created.id)]


@pytest.mark.parametrize(
    "image", ["catalog:beauty_hair/churros", f"file:{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp", "https://x.es/a.webp"]
)
def test_what_is_no_image_of_the_library_is_refused_and_nothing_changes(image_library, image):  # noqa: F811
    created = service()

    with pytest.raises(InvalidPayload) as refused:
        set_image(image, created.id)

    assert (refused.value.code, set(refused.value.fields)) == ("base.image_unknown", {"image"})
    assert Service.objects.get().image == ""


def test_an_employee_may_not_change_it(image_library):  # noqa: F811
    created = service()

    with pytest.raises(PermissionDenied):
        set_image(CUT, created.id, role="hub_employee")


# ── service.service.upload_image ───────────────────────────────────────────────────────────────────────────────


def test_a_photo_is_kept_as_a_webp_of_512_in_the_services_folder(hub_files):  # noqa: F811
    created = service()

    changed = upload(photo(), created.id)

    assert re.fullmatch(rf"file:{FOLDER}[0-9a-f]{{32}}\.webp", changed.image)
    assert changed.image_url == f"/p/media/{Hub.objects.get(slug='a').id.hex}/{changed.image.removeprefix('file:')}"
    assert PILImage.open(hub_files.open(key(changed.image))).size == (512, 512)


def test_a_new_photo_or_an_image_of_the_library_deletes_the_last_photo_once_saved(
    hub_files, image_library, django_capture_on_commit_callbacks  # noqa: F811
):
    created = service()
    first = upload(photo(), created.id).image

    with django_capture_on_commit_callbacks(execute=True):
        second = upload(photo((300, 300)), created.id).image
    assert not hub_files.exists(key(first)) and hub_files.exists(key(second))

    with django_capture_on_commit_callbacks(execute=True):
        set_image(CUT, created.id)
    assert not hub_files.exists(key(second))


def test_archiving_the_service_keeps_its_photo_for_when_it_is_restored(hub_files, django_capture_on_commit_callbacks):  # noqa: F811
    created = service()
    own = upload(photo(), created.id).image

    with django_capture_on_commit_callbacks(execute=True):
        run("service.service.archive", ServiceRefIn(id=created.id))
    restored = run("service.service.restore", ServiceRefIn(id=created.id))

    assert hub_files.exists(key(own))
    assert restored.image == own


def test_a_file_that_is_no_photo_is_refused(hub_files):  # noqa: F811
    created = service()

    with pytest.raises(InvalidPayload) as refused:
        upload(b"plain text", created.id)

    assert refused.value.code == "base.photo_invalid"
    assert Service.objects.get().image == ""


# ── service.service.suggest_image ──────────────────────────────────────────────────────────────────────────────


def test_it_suggests_the_librarys_images_for_its_name_and_sets_none(image_library):  # noqa: F811
    created = service("Corte de señora")
    Hub.objects.filter(slug="a").update(language="es")

    found = run("service.service.suggest_image", ServiceImageSuggestIn(id=created.id), "hub_employee")

    assert (found.query, [row.reference for row in found.rows]) == ("Corte de señora", [CUT])
    assert found.rows[0].title == "Corte de señora"
    assert Service.objects.get().image == ""


# ── Every read says it ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_list_the_detail_and_the_tills_catalog_say_the_image_and_its_url(image_library):  # noqa: F811
    created = service()
    set_image(CUT, created.id)
    expected = (CUT, "/p/catalog/beauty_hair/corte_senora.webp")

    [listed] = run("service.service.list", ServiceListIn()).rows
    detail = run("service.service.get", ServiceRefIn(id=created.id))
    [for_sale] = run("service.service.list_for_sale", ServiceForSaleIn()).rows

    assert (listed.image, listed.image_url) == expected
    assert (detail.image, detail.image_url) == expected
    assert (for_sale.image, for_sale.image_url) == expected


# ── Over HTTP ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_routes(client, make_user, image_library):  # noqa: F811
    created = service()
    client.force_login(make_user("boss", host="a", role="hub_admin"))

    response = client.post(
        "/api/service/services/image",
        json.dumps({"id": str(created.id), "image": CUT}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
    )
    found = client.get("/api/service/services/image/suggest", {"id": str(created.id)}, HTTP_HOST="a.localhost")

    assert response.status_code == 200, response.content
    assert response.json()["image"] == CUT
    assert found.status_code == 200, found.content
    assert uuid.UUID(found.json()["service_id"]) == created.id


def test_asked_for_a_services_photo_the_assistants_turn_offers_the_suggestion_and_the_set():
    from base import assistant

    tools = assistant.catalog(ctx_for("hub_admin"))
    offered = [op.name for op in assistant.relevant(tools, ["ponle foto al corte de señora"], "es")]

    assert {"service.service.suggest_image", "service.service.set_image"} <= set(offered)
    assert "service.service.upload_image" not in tools

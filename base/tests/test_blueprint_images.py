"""Images in a blueprint (INVENTORY-F33; round 2026-10-30): ``base.blueprint`` with ``base.images``.

A product's or a service's image of the shared library travels as its reference (``catalog:<folder>/<name>``): the
library is the same for every hub. A photo of its own travels inside the ``.blueprint.zip``, at ``media/<its name>``,
and loading the file copies it into the importing hub's prefix under a new UUIDv7 name, through the app's own upload
(``inventory.product.upload_image``: the plan's space counts it). Loading twice copies nothing twice (a product already
there is skipped, and its photo with it); undoing the load deletes the photos it copied. An image the library no
longer has, or a photo missing from the file or past the plan's space, loads its row without an image and the report
says why; a ``media/`` entry that is no WebP of 2 MB at most makes the file unreadable.

The ceilings: a photo is kept as a 512 × 512 WebP of 20–60 KB (``base.images``), already compressed, so a zip carries
about what its photos weigh: 300 photos of 60 KB are 18 MB, under :data:`blueprint.MAX_FILE_BYTES` (20 MB), in 1 000
entries at most; once inflated, 100 MB (the rows' JSON compresses ten to one, the photos not at all).
"""

import base64
import io
import json
import os
import re
import uuid
import zipfile

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.operations import get

from apps.inventory.models import Product
from base import blueprint
from base.models import Hub, Membership
from base.permissions import permissions_for
from base.storage import hub_prefix
from base.tests.test_image_catalog import IMAGES, webp, write_library
from base.tests.test_images import hub_files  # noqa: F401 - the store fixture

pytestmark = pytest.mark.django_db

A, B = Scope("host", "a"), Scope("host", "b")
FOLDER = "inventory/products/"
LATTE = "catalog:hospitality/cafe_con_leche"


def person(scope: Scope, username: str = "olga") -> OperationContext:
    user = get_user_model().objects.create_user(username=f"{username}-{scope.key}", password="pw")
    Membership.objects.create(user=user, host=scope.key, role=Membership.Role.OWNER)
    return OperationContext(scope=scope, actor=user, permissions=permissions_for(user, scope), language="es")


@pytest.fixture
def ctx():
    return person(A)


@pytest.fixture
def library(settings, tmp_path):
    """The library with the test's images and every image the seeds name."""
    seen = {(image["folder"], image["name"]) for image in IMAGES}
    extra = []
    for seed in blueprint.catalog():
        for key in ("inventory.product", "service.service"):
            for row in seed.bundle.data.get(key, []):
                if not row.get("image"):
                    continue
                folder, name = row["image"].removeprefix("catalog:").split("/")
                if (folder, name) not in seen:
                    seen.add((folder, name))
                    extra.append({"name": name, "folder": folder, "title": {"en": name, "es": name}, "tags": {}})
    settings.CATALOG_DIR = str(write_library(tmp_path / "img", [*IMAGES, *extra]))


def call(ctx, operation, /, **data):
    op = get(operation)
    return op(ctx, op.input(**data))


def product_row(name="Café con leche", sku="CAF-02", **fields):
    return {
        "name": name, "sku": sku, "price": 180, "cost": 0, "stock": "", "low_stock_threshold": "0", "unit": "ud",
        "ean13": "", "description": "", "tax_category_key": "restaurant.drink", "categories": [], "track_stock": False,
        "is_active": True, **fields,
    }  # fmt: skip


def bundle(rows, media=None, purpose="template"):
    return blueprint.Bundle(
        manifest=blueprint.manifest(
            name="Bar Pepe", language="es", country="ES", purpose=purpose, created_at="", vertical="restaurant",
            apps=["inventory"],
        ),
        data={"inventory.product": rows},
        media=media or {},
    )  # fmt: skip


def products(ctx) -> dict[str, Product]:
    return {product.sku: product for product in Product.objects.filter(is_deleted=False)}


def photo_of(ctx, name="Cortado", sku="CAF-03") -> tuple[str, bytes]:
    """A product with a photo of its own; its reference and the bytes kept."""
    made = call(ctx, "inventory.product.create", name=name, sku=sku, price=150, tax_category_key="restaurant.drink")
    buffer = io.BytesIO()
    from PIL import Image as PILImage

    PILImage.new("RGB", (600, 400), "brown").save(buffer, "PNG")
    reference = call(ctx, "inventory.product.upload_image", id=made.id, data_base64=base64.b64encode(buffer.getvalue()).decode()).image
    return reference, stored(A, reference)


def stored(scope: Scope, reference: str) -> bytes:
    from django.core.files.storage import storages

    hub = Hub.objects.get(slug=scope.key).id
    with storages["hub_files"].open(f"{hub_prefix(hub)}/{reference.removeprefix('file:')}", "rb") as file:
        return file.read()


def problems(result) -> list[str]:
    return [problem for app in result.report["apps"] for dataset in app["datasets"] for problem in dataset["problems"]]


# ── The seeds ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["restaurant.es", "hair_salon.en"])
def test_a_template_brings_each_product_and_service_with_its_image(ctx, library, key):
    seed = blueprint.template(key)

    result = blueprint.apply(ctx, seed.bundle, apps=None)

    assert problems(result) == []
    shown = {row.sku: row.image for row in call(ctx, "inventory.product.list", limit=100).rows}
    assert shown == {row["sku"]: row.get("image", "") for row in seed.bundle.data["inventory.product"]}
    if "service.service" in seed.bundle.data:
        services = {row.name: row.image for row in call(ctx, "service.service.list", limit=100).rows}
        assert services == {row["name"]: row.get("image", "") for row in seed.bundle.data["service.service"]}


def test_loading_a_template_again_changes_no_image(ctx, library):
    seed = blueprint.template("restaurant.es")
    blueprint.apply(ctx, seed.bundle, apps=None)
    before = {sku: (product.image, product.updated_at) for sku, product in products(ctx).items()}

    again = blueprint.apply(ctx, seed.bundle, apps=None)

    assert {sku: (product.image, product.updated_at) for sku, product in products(ctx).items()} == before
    assert again.created == {}


def test_an_image_the_library_no_longer_has_loads_the_product_without_it_and_says_why(ctx, library):
    result = blueprint.apply(ctx, bundle([product_row(image="catalog:hospitality/churros"), product_row("Agua", "BEB-01", image="")]), apps=None)

    assert {sku: product.image for sku, product in products(ctx).items()} == {"CAF-02": "", "BEB-01": ""}
    assert problems(result) == ["«Café con leche»: Esa imagen ya no está en la librería. Elige otra."]
    assert result.report["apps"][0]["datasets"][0]["status"] == "partial"


# ── Export: own photos inside, the library's by reference ──────────────────────────────────────────────────────


def test_an_export_carries_its_own_photos_inside_and_the_librarys_by_reference(ctx, library, hub_files):  # noqa: F811
    reference, kept = photo_of(ctx)
    latte = call(ctx, "inventory.product.create", name="Café con leche", sku="CAF-02", price=180, tax_category_key="restaurant.drink")
    call(ctx, "inventory.product.set_image", id=latte.id, image=LATTE)
    call(ctx, "inventory.product.create", name="Agua", sku="BEB-01", price=150, tax_category_key="restaurant.drink")

    exported = call(ctx, "base.blueprint.export", name="Bar Pepe", language="es", purpose="template", apps=["inventory"], data=["inventory"])

    with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported.content_base64))) as archive:
        names = sorted(archive.namelist())
        rows = {row["sku"]: row for row in json.loads(archive.read("data/inventory.product.json"))}
        assert archive.read(f"media/{reference.removeprefix('file:')}") == kept
    assert names == ["data/inventory.product.json", "manifest.json", f"media/{reference.removeprefix('file:')}"]
    assert (rows["CAF-03"]["image"], rows["CAF-02"]["image"]) == (reference, LATTE)
    assert "image" not in rows["BEB-01"]


def test_a_photo_that_is_gone_from_the_store_is_exported_without_it(ctx, library, hub_files):  # noqa: F811
    reference, _ = photo_of(ctx)
    hub_files.delete(f"{hub_prefix(Hub.objects.get(slug='a').id)}/{reference.removeprefix('file:')}")

    data = blueprint.export_data(ctx, {"inventory": ["inventory.product"]}, purpose="template")

    assert blueprint.export_media(ctx, data) == {}
    assert "image" not in data["inventory.product"][0]


# ── Import: each photo copied under a new name ────────────────────────────────────────────────────────────────


def test_loading_the_file_in_another_business_copies_each_photo_under_a_new_name(ctx, library, hub_files):  # noqa: F811
    reference, kept = photo_of(ctx)
    data = blueprint.export_data(ctx, {"inventory": ["inventory.product"]}, purpose="template")
    media = blueprint.export_media(ctx, data)
    # Phase 1 keeps every hub's products in one table: another SKU, so B's load creates its own product.
    data["inventory.product"][0]["sku"] = "B-CAF-03"
    content = blueprint.write_zip(bundle(data["inventory.product"], media))
    other = person(B)

    result = blueprint.apply(other, blueprint.read_zip(content), apps=None)

    assert problems(result) == []
    copy = products(other)["B-CAF-03"].image
    assert re.fullmatch(rf"file:{FOLDER}[0-9a-f]{{32}}\.webp", copy) and copy != reference
    assert uuid.UUID(copy.removeprefix(f"file:{FOLDER}").removesuffix(".webp")).version == 7
    assert stored(B, copy) == kept


def test_loading_it_twice_copies_no_photo_twice(ctx, library, hub_files):  # noqa: F811
    reference, kept = photo_of(ctx)
    loaded = bundle([product_row("Cortado", "CAF-09", image=reference)], {reference.removeprefix("file:"): kept})
    other = person(B)
    blueprint.apply(other, loaded, apps=None)
    hub = Hub.objects.get(slug="b").id
    before = hub_files.listdir(f"{hub_prefix(hub)}/{FOLDER}")[1]

    blueprint.apply(other, loaded, apps=None)

    assert hub_files.listdir(f"{hub_prefix(hub)}/{FOLDER}")[1] == before and len(before) == 1


def test_a_photo_missing_from_the_file_loads_the_product_without_it_and_says_why(ctx, library, hub_files):  # noqa: F811
    result = blueprint.apply(ctx, bundle([product_row(image=f"file:{FOLDER}{uuid.uuid7().hex}.webp")]), apps=None)

    assert products(ctx)["CAF-02"].image == ""
    assert problems(result) == ["«Café con leche»: su foto no viene en el archivo, así que entra sin ella."]


def test_a_photo_past_the_plans_space_loads_the_product_without_it_and_says_why(ctx, library, hub_files):  # noqa: F811
    name = f"{FOLDER}{uuid.uuid7().hex}.webp"
    Hub.objects.filter(slug="a").update(state={"plan": {"max_storage_bytes": 10}})

    result = blueprint.apply(ctx, bundle([product_row(image=f"file:{name}")], {name: webp()}), apps=None)

    assert products(ctx)["CAF-02"].image == ""
    [problem] = problems(result)
    assert problem.startswith("«Café con leche»: No queda espacio para ese archivo")


def test_undoing_the_load_deletes_the_photos_it_copied(ctx, library, hub_files, django_capture_on_commit_callbacks):  # noqa: F811
    name = f"{FOLDER}{uuid.uuid7().hex}.webp"
    result = blueprint.apply(ctx, bundle([product_row(image=f"file:{name}")], {name: webp()}), apps=None)
    copy = products(ctx)["CAF-02"].image

    with django_capture_on_commit_callbacks(execute=True):
        blueprint.undo(ctx, result.created)

    assert copy.startswith("file:")
    assert not hub_files.exists(f"{hub_prefix(Hub.objects.get(slug='a').id)}/{copy.removeprefix('file:')}")


def test_a_service_travels_with_its_image(ctx, library):
    made = call(ctx, "service.service.create", name="Corte de señora", tax_category_key="service.generic", price=2500)
    call(ctx, "service.service.set_image", id=made.id, image="catalog:beauty_hair/corte_senora")

    data = blueprint.export_data(ctx, {"service": ["service.service"]}, purpose="template")
    assert data["service.service"][0]["image"] == "catalog:beauty_hair/corte_senora"
    # Phase 1 keeps every hub's services in one table: another name, so B's load creates its own service.
    data["service.service"][0]["name"] = "Corte de señora (B)"
    other = person(B)

    result = blueprint.apply(other, blueprint.Bundle(manifest=bundle([]).manifest, data=data), apps={"service"})

    assert problems(result) == [] and result.created["service.service"]
    images = {row.name: row.image for row in call(other, "service.service.list", limit=10).rows}
    assert images["Corte de señora (B)"] == "catalog:beauty_hair/corte_senora"


# ── The file: what a media/ entry may be, and the ceilings ─────────────────────────────────────────────────────


def zip_with_media(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json.dumps(bundle([]).manifest))
        archive.writestr("data/inventory.product.json", "[]")
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def a_webp(size: int) -> bytes:
    """``size`` bytes that start as a WebP does (a RIFF container of the WEBP kind)."""
    return b"RIFF" + (size - 8).to_bytes(4, "little") + b"WEBP" + os.urandom(size - 12)


def test_a_written_file_reads_back_with_its_photos():
    name = f"{FOLDER}{uuid.uuid7().hex}.webp"
    written = bundle([product_row(image=f"file:{name}")], {name: webp()})

    assert blueprint.read_zip(blueprint.write_zip(written)) == written


@pytest.mark.parametrize(
    ("entry", "content", "reason"),
    [
        (f"media/{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp", b"\x89PNG\r\n\x1a\n" + b"0" * 40, "bad_photo"),
        (f"media/{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp", None, "bad_photo"),
        ("media/../evil.webp", a_webp(100), "unreadable"),
        ("media/inventory/x.webp", a_webp(100), "unreadable"),
        (f"media/{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.png", a_webp(100), "unreadable"),
    ],
    ids=["not_a_webp", "past_2_mb", "climbing_out", "not_a_photo_name", "not_webp_named"],
)
def test_a_media_entry_that_is_no_photo_of_ours_makes_the_file_unreadable(entry, content, reason):
    content = a_webp(2 * 1024 * 1024 + 1) if content is None else content

    with pytest.raises(blueprint.BlueprintInvalid) as refused:
        blueprint.read_zip(zip_with_media({entry: content}))

    assert refused.value.reason == reason
    assert str(refused.value)


def test_the_ceilings_fit_three_hundred_photos():
    assert (blueprint.MAX_FILE_BYTES, blueprint.MAX_INFLATED_BYTES, blueprint.MAX_ENTRIES) == (
        20 * 1024 * 1024, 100 * 1024 * 1024, 1000,
    )
    photos = {f"media/{FOLDER}{uuid.uuid7().hex}.webp": a_webp(60 * 1024) for _ in range(300)}

    content = zip_with_media(photos)

    assert len(content) <= blueprint.MAX_FILE_BYTES
    assert len(blueprint.read_zip(content).media) == 300


def test_past_a_thousand_entries_the_file_is_refused():
    photos = {f"media/{FOLDER}{uuid.uuid7().hex}.webp": a_webp(20) for _ in range(blueprint.MAX_ENTRIES - 1)}

    with pytest.raises(blueprint.BlueprintInvalid) as refused:
        blueprint.read_zip(zip_with_media(photos))

    assert refused.value.reason == "unreadable"


def test_a_file_past_20_mb_is_said_so():
    with pytest.raises(blueprint.BlueprintInvalid) as refused:
        blueprint.read_zip(b"0" * (blueprint.MAX_FILE_BYTES + 1))

    assert "20 MB" in str(refused.value)

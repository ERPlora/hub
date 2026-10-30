"""The shared image library (round 2026-10-30, «blueprints con imágenes»): ``base.image_catalog``.

ERPlora/blueprints publishes ``img/<folder>/<name>.webp`` and ``img/catalog.json`` once for every hub: in AWS under
``shared/catalog/`` of the hubs' bucket, locally in the checkout beside this repo (``CATALOG_DIR``). The manifest names
each image in English and Spanish with its search words; the Hub reads it (kept 10 minutes, read again when the file
changes on disk), finds an image by what a product is called in either language, and serves the image at
``/p/catalog/<folder>/<name>.webp`` to anyone, cached for a year: the library is nobody's data. A row points at an
image with ``catalog:<folder>/<name>``, never with a URL.
"""

import io
import json
import os
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.urls import resolve
from live.context import OperationContext, Scope
from live.errors import NotFound, OperationError, PermissionDenied
from live.operations import get
from PIL import Image as PILImage

from base import image_catalog
from base.schemas import CatalogImageRefIn, CatalogImageSearchIn

A = Scope("host", "a")
HOME = "base.view_home"
YEAR = "public, max-age=31536000, immutable"
#: base/tests/test_api.py's map of the SPA's routes takes these too.
CATALOG_IMAGE_ROUTES = {
    ("GET", "/catalog/images", "base.catalog_image.search"),
    ("GET", "/catalog/images/detail", "base.catalog_image.get"),
}

#: A small library as ERPlora/blueprints writes its manifest (the real one has 491 images).
IMAGES = [
    {
        "name": "cafe_con_leche",
        "folder": "hospitality",
        "title": {"en": "White coffee", "es": "Café con leche"},
        "tags": {"en": ["coffee", "milk", "latte"], "es": ["café", "leche", "manchado"]},
    },
    {
        "name": "latte",
        "folder": "hospitality",
        "title": {"en": "Latte", "es": "Café latte"},
        "tags": {"en": ["coffee", "milk"], "es": ["café", "leche"]},
    },
    {
        "name": "cafe_solo",
        "folder": "hospitality",
        "title": {"en": "Espresso", "es": "Café solo"},
        "tags": {"en": ["coffee", "black coffee"], "es": ["café", "expreso"]},
    },
    {
        "name": "patatas_bravas",
        "folder": "hospitality",
        "title": {"en": "Patatas bravas", "es": "Patatas bravas"},
        "tags": {"en": ["potatoes", "spicy"], "es": ["patatas", "tapa"]},
    },
    {
        "name": "corte_senora",
        "folder": "beauty_hair",
        "title": {"en": "Women's haircut", "es": "Corte de señora"},
        "tags": {"en": ["haircut", "women"], "es": ["corte", "mujer"]},
    },
]


def webp(colour: str = "red", size: tuple[int, int] = (512, 512)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", size, colour).save(buffer, "WEBP", quality=85)
    return buffer.getvalue()


def write_library(root: Path, images: list[dict] = IMAGES) -> Path:
    """``root`` laid out as ERPlora/blueprints' ``img/``: a WebP per image and ``catalog.json``."""
    for image in images:
        path = root / image["folder"] / f"{image['name']}.webp"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(webp())
    (root / "catalog.json").write_text(json.dumps({"version": 1, "images": images}), encoding="utf-8")
    return root


@pytest.fixture
def image_library(settings, tmp_path) -> Path:
    """The library on disk, where ``CATALOG_DIR`` points (as locally, without a bucket)."""
    root = write_library(tmp_path / "img")
    settings.CATALOG_DIR = str(root)
    return root


def names(images) -> list[str]:
    return [f"{image.folder}/{image.name}" for image in images]


def ctx_with(*permissions, language: str = "en") -> OperationContext:
    return OperationContext(scope=A, actor="ana", permissions=frozenset(permissions), language=language)


# ── The manifest ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_it_reads_every_image_of_the_manifest_with_its_titles_and_words(image_library):
    library = image_catalog.library()

    espresso = library.get("hospitality", "cafe_solo")
    assert (espresso.title_in("en"), espresso.title_in("es")) == ("Espresso", "Café solo")
    assert espresso.reference == "catalog:hospitality/cafe_solo"
    assert espresso.url == "/p/catalog/hospitality/cafe_solo.webp"
    assert len(library.images) == len(IMAGES)


def test_a_language_the_manifest_does_not_have_reads_the_english_title(image_library):
    assert image_catalog.library().get("hospitality", "cafe_solo").title_in("fr") == "Espresso"


def test_an_entry_that_is_no_image_reference_is_left_out_and_the_rest_is_read(image_library):
    broken = [
        {"name": "Bad Name", "folder": "hospitality", "title": {"en": "x", "es": "x"}, "tags": {}},
        {"name": "ok", "folder": "../etc", "title": {"en": "x", "es": "x"}, "tags": {}},
        {"name": "untitled", "folder": "hospitality", "title": {"es": "Sin inglés"}, "tags": {}},
        "not an object",
    ]
    (image_library / "catalog.json").write_text(json.dumps({"version": 1, "images": [*IMAGES, *broken]}))

    assert len(image_catalog.library().images) == len(IMAGES)


@pytest.mark.parametrize("content", ["", "{not json", json.dumps({"version": 1}), json.dumps([1, 2])])
def test_a_manifest_that_cannot_be_read_makes_the_library_unavailable(image_library, content):
    (image_library / "catalog.json").write_text(content)

    with pytest.raises(image_catalog.LibraryUnavailable):
        image_catalog.library()


def test_no_manifest_at_all_makes_the_library_unavailable(settings, tmp_path):
    settings.CATALOG_DIR = str(tmp_path / "nowhere")

    with pytest.raises(image_catalog.LibraryUnavailable):
        image_catalog.library()


def test_the_manifest_is_read_again_when_its_file_changes(image_library):
    assert image_catalog.library().get("hospitality", "churros") is None
    churros = {"name": "churros", "folder": "hospitality", "title": {"en": "Churros", "es": "Churros"}, "tags": {}}
    manifest = image_library / "catalog.json"
    manifest.write_text(json.dumps({"version": 1, "images": [*IMAGES, churros]}))
    later = manifest.stat().st_mtime_ns + 5_000_000_000
    os.utime(manifest, ns=(later, later))

    assert image_catalog.library().get("hospitality", "churros") is not None


def test_the_manifest_is_kept_and_read_once_while_it_does_not_change(image_library, monkeypatch):
    image_catalog.library()
    reads = []
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: reads.append(self) or original(self))

    image_catalog.library()

    assert reads == []


def test_in_the_bucket_it_reads_the_shared_prefix_and_keeps_it_ten_minutes(settings, monkeypatch):
    settings.CATALOG_DIR = ""
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    from django.core.files.storage import storages

    store: InMemoryStorage = storages["hub_files"]
    store.save("shared/catalog/catalog.json", ContentFile(json.dumps({"version": 1, "images": IMAGES[:1]})))
    store.save("shared/catalog/hospitality/cafe_con_leche.webp", ContentFile(webp()))
    clock = [1000.0]
    monkeypatch.setattr(image_catalog, "_now", lambda: clock[0])

    assert names(image_catalog.library().images) == ["hospitality/cafe_con_leche"]
    store.delete("shared/catalog/catalog.json")
    store.save("shared/catalog/catalog.json", ContentFile(json.dumps({"version": 1, "images": IMAGES[:2]})))
    clock[0] += image_catalog.TTL_SECONDS - 1
    assert len(image_catalog.library().images) == 1
    clock[0] += 2
    assert len(image_catalog.library().images) == 2
    assert image_catalog.open_image(image_catalog.library().get("hospitality", "cafe_con_leche")).read() == webp()


# ── References ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("reference", "parsed"),
    [
        ("catalog:hospitality/cafe_solo", ("hospitality", "cafe_solo")),
        ("catalog:beauty_hair/corte_senora", ("beauty_hair", "corte_senora")),
        ("catalog:Hospitality/cafe_solo", None),
        ("catalog:hospitality/cafe_solo.webp", None),
        ("catalog:hospitality/../x", None),
        ("catalog:/cafe_solo", None),
        ("https://cdn.example.com/hospitality/cafe_solo.webp", None),
        ("file:inventory/products/0193.webp", None),
        ("", None),
    ],
)
def test_a_catalog_reference_names_a_folder_and_an_image(reference, parsed):
    assert image_catalog.parse_reference(reference) == parsed


def test_exists_says_whether_the_library_has_the_image(image_library):
    assert image_catalog.exists("catalog:hospitality/cafe_solo")
    assert not image_catalog.exists("catalog:hospitality/churros")
    assert not image_catalog.exists("catalog:retail/cafe_solo")
    assert not image_catalog.exists("hospitality/cafe_solo")


# ── Search ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_exact_title_comes_first_then_a_title_that_contains_it_then_a_search_word(image_library):
    found = image_catalog.library().search("leche", "es")

    assert names(found)[:2] == ["hospitality/cafe_con_leche", "hospitality/latte"]


def test_an_exact_title_ranks_above_a_title_that_only_contains_it(image_library):
    assert names(image_catalog.library().search("Latte", "en"))[:2] == ["hospitality/latte", "hospitality/cafe_con_leche"]


def test_it_ignores_accents_and_case(image_library):
    assert names(image_catalog.library().search("CAFE SOLO", "es"))[0] == "hospitality/cafe_solo"
    assert names(image_catalog.library().search("senora", "es")) == ["beauty_hair/corte_senora"]


def test_the_words_may_come_in_any_order(image_library):
    assert names(image_catalog.library().search("leche con café", "es"))[0] == "hospitality/cafe_con_leche"


def test_a_name_in_the_other_language_finds_its_image_too(image_library):
    assert names(image_catalog.library().search("Café con leche", "en"))[0] == "hospitality/cafe_con_leche"
    assert names(image_catalog.library().search("espresso", "es"))[0] == "hospitality/cafe_solo"


def test_a_plural_finds_the_singular(image_library):
    assert names(image_catalog.library().search("haircuts", "en")) == ["beauty_hair/corte_senora"]


def test_nothing_alike_finds_nothing(image_library):
    assert image_catalog.library().search("paella", "es") == []


def test_no_words_lists_the_folder_by_title(image_library):
    found = image_catalog.library().search("", "es", folder="hospitality")

    assert [image.title_in("es") for image in found] == ["Café con leche", "Café latte", "Café solo", "Patatas bravas"]


def test_a_folder_narrows_the_search(image_library):
    assert image_catalog.library().search("corte", "es", folder="hospitality") == []


# ── base.catalog_image.search and base.catalog_image.get ─────────────────────────────────────────────────────────


def test_search_is_a_read_for_everyone_of_the_hub_and_a_tool_of_the_assistant():
    op = get("base.catalog_image.search")

    assert (op.kind, op.permission) == ("query", HOME)
    assert "image" in op.ai["description"] and "library" in op.ai["description"]


def test_search_answers_the_best_images_first_titled_in_the_persons_language(image_library):
    page = get("base.catalog_image.search")(ctx_with(HOME, language="es"), CatalogImageSearchIn(query="leche"))

    first = page.rows[0].model_dump()
    assert first == {
        "reference": "catalog:hospitality/cafe_con_leche",
        "folder": "hospitality",
        "name": "cafe_con_leche",
        "title": "Café con leche",
        "url": "/p/catalog/hospitality/cafe_con_leche.webp",
    }
    assert (page.total, page.limit, page.offset) == (2, 20, 0)


def test_search_pages_its_answer(image_library):
    page = get("base.catalog_image.search")(ctx_with(HOME), CatalogImageSearchIn(query="", limit=2, offset=2))

    # By title in English: Espresso, Latte, Patatas bravas, White coffee, Women's haircut.
    assert ([row.name for row in page.rows], page.total) == (["patatas_bravas", "cafe_con_leche"], 5)


def test_search_needs_the_home(image_library):
    with pytest.raises(PermissionDenied):
        get("base.catalog_image.search")(ctx_with(), CatalogImageSearchIn(query="leche"))


def test_search_says_when_the_library_cannot_be_read(settings, tmp_path):
    settings.CATALOG_DIR = str(tmp_path / "nowhere")

    with pytest.raises(OperationError) as refused:
        get("base.catalog_image.search")(ctx_with(HOME), CatalogImageSearchIn(query="leche"))

    assert (refused.value.status, refused.value.code) == (503, "base.image_library_unavailable")
    assert "image library" in refused.value.message


def test_it_is_said_in_the_persons_language(settings, tmp_path, image_library):
    with pytest.raises(NotFound) as missing:
        get("base.catalog_image.get")(ctx_with(HOME, language="es"), CatalogImageRefIn(reference="catalog:x/y"))
    settings.CATALOG_DIR = str(tmp_path / "nowhere")
    with pytest.raises(OperationError) as refused:
        get("base.catalog_image.search")(ctx_with(HOME, language="es"), CatalogImageSearchIn(query="leche"))

    assert missing.value.message == "Esta imagen no está en la librería de imágenes."
    assert refused.value.message == "La librería de imágenes no se puede leer ahora. Inténtalo de nuevo en un rato."


@pytest.mark.parametrize("folder", ["../etc", "Hospitality", "a/b"])
def test_search_refuses_a_folder_that_is_no_folder(folder):
    with pytest.raises(ValueError):
        CatalogImageSearchIn(query="", folder=folder)


def test_get_names_an_image_by_its_reference_in_the_persons_language(image_library):
    image = get("base.catalog_image.get")(ctx_with(HOME, language="es"), CatalogImageRefIn(reference="catalog:hospitality/cafe_solo"))

    assert (image.title, image.url) == ("Café solo", "/p/catalog/hospitality/cafe_solo.webp")


@pytest.mark.parametrize("reference", ["catalog:hospitality/churros", "file:inventory/products/x.webp", "cafe_solo"])
def test_get_does_not_find_what_the_library_does_not_have(image_library, reference):
    with pytest.raises(NotFound):
        get("base.catalog_image.get")(ctx_with(HOME), CatalogImageRefIn(reference=reference))


def test_both_are_bound_to_their_routes():
    from base.api import router

    for method, path, name in CATALOG_IMAGE_ROUTES:
        [route] = router.path_operations[path].operations
        assert (route.methods, route.operation_id) == ([method], name)
        assert resolve(f"/api{path}").url_name


@pytest.mark.django_db
def test_an_employee_searches_over_http_and_a_stranger_does_not(client, make_user, image_library):
    url = "/api/catalog/images?query=bravas"
    assert client.get(url, HTTP_HOST="a.localhost:8000").status_code in (401, 403)

    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = client.get(url, HTTP_HOST="a.localhost:8000")

    assert response.status_code == 200, response.content
    assert [row["reference"] for row in response.json()["rows"]] == ["catalog:hospitality/patatas_bravas"]


# ── /p/catalog/<folder>/<name>.webp ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_an_image_is_served_to_anyone_cached_for_a_year(client, image_library):
    response = client.get("/p/catalog/hospitality/cafe_solo.webp", HTTP_HOST="a.localhost:8000")

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == webp()
    assert (response["Content-Type"], response["Cache-Control"]) == ("image/webp", YEAR)
    assert "sandbox" in response["Content-Security-Policy"]
    assert not response.cookies


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/p/catalog/hospitality/churros.webp",
        "/p/catalog/hospitality/cafe_solo.png",
        "/p/catalog/hospitality/cafe_solo",
        "/p/catalog/hospitality/catalog.json",
        "/p/catalog/Hospitality/cafe_solo.webp",
        "/p/catalog/stray/stray.webp",
    ],
)
def test_what_the_manifest_does_not_name_is_not_found(client, image_library, path):
    (image_library / "stray").mkdir()
    (image_library / "stray" / "stray.webp").write_bytes(webp())

    assert client.get(path, HTTP_HOST="a.localhost:8000").status_code == 404


@pytest.mark.django_db
def test_an_image_named_in_the_manifest_but_missing_is_not_found(client, image_library):
    (image_library / "hospitality" / "cafe_solo.webp").unlink()

    assert client.get("/p/catalog/hospitality/cafe_solo.webp", HTTP_HOST="a.localhost:8000").status_code == 404


@pytest.mark.django_db
def test_without_a_library_an_image_is_not_found(client, settings, tmp_path):
    settings.CATALOG_DIR = str(tmp_path / "nowhere")

    assert client.get("/p/catalog/hospitality/cafe_solo.webp", HTTP_HOST="a.localhost:8000").status_code == 404

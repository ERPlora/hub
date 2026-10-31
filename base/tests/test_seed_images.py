"""The Hub's templates bring every product and service with an image of the shared library (round 2026-10-30;
INVENTORY-F33 step 3, SERVICE-F34): ``base/seeds/<vertical>.<language>.json``.

Each row of ``inventory.product`` and ``service.service`` names an image with ``catalog:<folder>/<name>``: the
restaurant's from ``hospitality/`` (two from ``retail/``, the only honest pictures the library has for them), the hair
salon's from ``beauty_hair/``. The reference must be in the real manifest of ERPlora/blueprints (``img/catalog.json``),
checked out beside this repo (CI clones it there): without it these tests fail, they never skip. A file's name may lie
about its picture (``patatas_bravas.webp`` shows onion rings): an image is chosen by its title and its words, and each
one shares a word with what the product is called in the seed's language, or says here why not.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings

from base import image_catalog
from base.blueprint import SEEDS_DIR

#: The datasets whose rows show an image on the till.
WITH_IMAGE = ("inventory.product", "service.service")
#: Rows whose image shares no word with their name, and why it is still the honest one.
NO_SHARED_WORD = {
    ("restaurant.es", "PRI-02"): "The library has no sea bass: a skewer of grilled sardines is its only grilled fish.",
    ("restaurant.en", "STA-02"): "The library has no patatas bravas: fried potatoes, the closest (es: «Patatas fritas»).",
    ("hair_salon.es", "Peinado"): "This seed's «Peinado» is a blow-dry (en «Blow-dry»), «Secado con cepillo» in the library.",
}
#: Pictures of a third party's product (its brand, label, pack or trade dress, such as the Coca-Cola contour bottle),
#: which ERPlora/blueprints drops: no seed may point at one, whether the manifest at hand still lists it or not.
THIRD_PARTY_BRANDS = frozenset(
    {
        "hospitality/coca_cola",
        "hospitality/sprite",
        "hospitality/coca_cola_zero",
        "hospitality/aquarius",
        "hospitality/fanta_limon",
        "hospitality/fanta_naranja",
        "hospitality/cerveza_sin",
        "retail/coca_cola_2l",
        "retail/detergente",
        "retail/gel_ducha",
        "retail/pasta_dientes",
        "retail/yogur_natural",
        "retail/carne_picada",
        "retail/desodorante",
        "retail/tomates_kg",
    }
)


def seeds() -> dict[str, dict]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(SEEDS_DIR.glob("*.json"))}


def rows_with_image():
    for key, seed in seeds().items():
        for dataset in WITH_IMAGE:
            for row in seed["data"].get(dataset, []):
                yield key, dataset, row


def references(value) -> list[str]:
    """Every ``catalog:<folder>/<name>`` a seed names, as ``<folder>/<name>``, wherever in the seed it is."""
    if isinstance(value, dict):
        return [found for item in value.values() for found in references(item)]
    if isinstance(value, list):
        return [found for item in value for found in references(item)]
    parsed = image_catalog.parse_reference(value) if isinstance(value, str) else None
    return ["/".join(parsed)] if parsed else []


def row_key(dataset: str, row: dict) -> str:
    return row["sku"] if dataset == "inventory.product" else row["name"]


def real_library() -> image_catalog.Library:
    """The manifest of the ERPlora/blueprints checkout this deployment reads (``CATALOG_DIR``)."""
    root = Path(settings.CATALOG_DIR or settings.BASE_DIR.parent / "blueprints" / "img")
    if not (root / image_catalog.MANIFEST).is_file():
        pytest.fail(
            f"The shared image library is not at {root}: ERPlora/blueprints is a private repo, so clone it beside "
            "this repo with a GitHub account that has access to it (gh repo clone ERPlora/blueprints ../blueprints) "
            "or point CATALOG_DIR at its img/."
        )
    return image_catalog._parse((root / image_catalog.MANIFEST).read_bytes())


def words(text: str) -> set[str]:
    return {word[:-1] if len(word) > 3 and word.endswith("s") else word for word in image_catalog.fold(text).split()} - {
        *image_catalog.STOPWORDS
    }


def test_no_product_is_left_without_an_image():
    missing = [(key, row_key(dataset, row)) for key, dataset, row in rows_with_image() if not row.get("image")]

    assert missing == []
    assert len(list(rows_with_image())) == 16 + 16 + 13 + 13


def test_every_seed_image_reference_exists_in_the_manifest():
    library = real_library()

    unknown = [
        (key, row_key(dataset, row), row["image"])
        for key, dataset, row in rows_with_image()
        if (parsed := image_catalog.parse_reference(row.get("image", ""))) is None or library.get(*parsed) is None
    ]

    assert unknown == []


def test_no_seed_points_at_a_third_party_brand():
    branded = [
        (key, reference) for key, seed in seeds().items() for reference in references(seed) if reference in THIRD_PARTY_BRANDS
    ]

    assert branded == [], (
        f"These seed images show a third party's brand (its product, label or trade dress), which the library drops: "
        f"{branded}. Pick a generic picture of the same thing."
    )


def test_the_brand_check_finds_a_reference_anywhere_in_a_seed():
    seed = {
        "data": {"inventory.product": [{"image": "catalog:hospitality/coca_cola"}], "other": {"x": ["catalog:retail/detergente"]}}
    }

    assert references(seed) == ["hospitality/coca_cola", "retail/detergente"]


def test_the_restaurant_shows_hospitality_and_the_hair_salon_its_hair_folder():
    folders = {(key.split(".")[0], row["image"].split(":")[1].split("/")[0]) for key, _, row in rows_with_image()}

    assert folders == {("restaurant", "hospitality"), ("restaurant", "retail"), ("hair_salon", "beauty_hair")}


def test_each_image_shows_what_the_product_is_called_in_the_seeds_language():
    library = real_library()
    unexplained = []
    for key, dataset, row in rows_with_image():
        image = library.get(*image_catalog.parse_reference(row["image"]))
        language = key.split(".")[1]
        said = words(image.title_in(language)) | {
            word for tag in image.words[language].tags for word in words(tag)
        }
        if not words(row["name"]) & said and (key, row_key(dataset, row)) not in NO_SHARED_WORD:
            unexplained.append((key, row["name"], row["image"], image.title_in(language)))

    assert unexplained == []


def test_every_exception_is_still_needed():
    library = real_library()
    rows = {(key, row_key(dataset, row)): (row, key.split(".")[1]) for key, dataset, row in rows_with_image()}

    for exception in NO_SHARED_WORD:
        row, language = rows[exception]
        image = library.get(*image_catalog.parse_reference(row["image"]))
        said = words(image.title_in(language)) | {word for tag in image.words[language].tags for word in words(tag)}
        assert not words(row["name"]) & said, exception

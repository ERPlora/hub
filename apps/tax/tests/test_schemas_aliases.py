"""The aliases of the tax categories, normalised the same way at every door."""

import pytest

from apps.tax.schemas.aliases import AliasIn, AliasListIn, AliasResolveIn, normalize_text

from .schema_checks import invalid_fields


def test_alias_list_filters_and_sort():
    assert AliasListIn().model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "alias": None,
        "tax_category_key": None,
        "source": None,
        "sort": "alias",
        "dir": "asc",
    }
    assert invalid_fields(AliasListIn, source="manual") == {"source"}
    for sort in ("alias", "tax_category_key", "source", "is_active", "id"):
        assert AliasListIn(sort=sort).sort == sort


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("Beer", "beer"),
        ("  IVA   10 ", "iva 10"),
        ("Comida\tcasera", "comida casera"),
        ("ÁLCOHOL", "álcohol"),
    ],
)
def test_normalize_text(text, normalized):
    assert normalize_text(text) == normalized


def test_alias_in_is_normalised():
    alias = AliasIn(alias="  Cerveza  Artesana ", tax_category_key="restaurant.alcohol")
    assert (alias.alias, alias.source) == ("cerveza artesana", "learned")
    assert (
        AliasIn(
            alias="beer", tax_category_key="restaurant.alcohol", source="shipped"
        ).source
        == "shipped"
    )
    assert invalid_fields(
        AliasIn, alias="   ", tax_category_key="restaurant.alcohol"
    ) == {"alias"}
    assert invalid_fields(
        AliasIn, alias="x" * 201, tax_category_key="restaurant.alcohol"
    ) == {"alias"}
    assert invalid_fields(
        AliasIn, alias="beer", tax_category_key="restaurant.alcohol", source="manual"
    ) == {"source"}


def test_alias_resolve():
    assert AliasResolveIn(text=" BEER ").text == "beer"
    assert invalid_fields(AliasResolveIn, text="") == {"text"}

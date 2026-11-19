"""The fourteen allergens every app reads: their codes and order, their names, what a schema takes and a CSV cell says."""

import pytest
from django.utils import translation
from pydantic import ValidationError

from base import allergens
from base.allergens import AllergensCellIn, AllergensIn, AllergensOut, AllergensPatchIn

THE_FOURTEEN = [
    "gluten",
    "crustaceans",
    "egg",
    "fish",
    "peanut",
    "soy",
    "milk",
    "tree_nuts",
    "celery",
    "mustard",
    "sesame",
    "sulphites",
    "lupin",
    "molluscs",
]
ENGLISH = [
    "Gluten",
    "Crustaceans",
    "Egg",
    "Fish",
    "Peanut",
    "Soy",
    "Milk",
    "Tree nuts",
    "Celery",
    "Mustard",
    "Sesame",
    "Sulphites",
    "Lupin",
    "Molluscs",
]
SPANISH = [
    "Gluten",
    "Crustáceos",
    "Huevo",
    "Pescado",
    "Cacahuete",
    "Soja",
    "Leche",
    "Frutos de cáscara",
    "Apio",
    "Mostaza",
    "Sésamo",
    "Sulfitos",
    "Altramuces",
    "Moluscos",
]


class Declared(AllergensIn):
    pass


class Changed(AllergensPatchIn):
    pass


class Shown(AllergensOut):
    pass


class Row(AllergensCellIn):
    pass


# The list


def test_the_list_is_the_fourteen_of_the_regulation_in_its_order():
    assert list(allergens.CODES) == THE_FOURTEEN
    assert [code for code, _name in allergens.ALLERGENS] == THE_FOURTEEN


@pytest.mark.parametrize(("language", "names"), [("en", ENGLISH), ("es", SPANISH)])
def test_each_allergen_is_named_in_the_persons_language(language, names):
    with translation.override(language):
        assert [str(name) for _code, name in allergens.ALLERGENS] == names


def test_their_names_are_said_in_the_order_of_the_list_whatever_order_they_come_in():
    with translation.override("es"):
        assert allergens.names(["milk", "gluten", "tree_nuts"]) == "Gluten, Leche, Frutos de cáscara"
    with translation.override("en"):
        assert allergens.names(["milk", "gluten"]) == "Gluten, Milk"
    assert allergens.names([]) == ""


# What a schema takes


def test_a_schema_keeps_each_allergen_once_in_the_order_of_the_list():
    assert Declared(allergens=["milk", "gluten", "milk"]).allergens == ["gluten", "milk"]
    assert Declared().allergens == []


def test_a_change_that_does_not_send_them_leaves_them_alone_and_an_empty_one_clears_them():
    assert Changed().allergens is None
    assert Changed(allergens=[]).allergens == []
    assert Changed(allergens=["sesame", "egg"]).allergens == ["egg", "sesame"]


@pytest.mark.parametrize("schema", [Declared, Changed])
def test_an_allergen_off_the_list_is_refused_on_its_field(schema):
    with pytest.raises(ValidationError) as refused:
        schema(allergens=["gluten", "shellfish"])
    (error,) = refused.value.errors()
    assert (error["loc"], error["type"]) == (("allergens",), "value_error")


@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("en", "That allergen is not one of the fourteen that must be declared."),
        ("es", "Ese alérgeno no es uno de los catorce de declaración obligatoria."),
    ],
)
def test_the_refusal_is_said_in_the_persons_language(language, message):
    with translation.override(language), pytest.raises(ValidationError) as refused:
        Declared(allergens=["shellfish"])
    assert str(refused.value.errors()[0]["ctx"]["error"]) == message


def test_no_list_carries_more_allergens_than_there_are():
    with pytest.raises(ValidationError) as refused:
        Declared(allergens=THE_FOURTEEN + ["gluten"])
    assert refused.value.errors()[0]["type"] == "too_long"


@pytest.mark.parametrize("schema", [Declared, Changed, Shown])
def test_what_a_tool_or_an_integrator_reads_lists_the_fourteen_codes(schema):
    field = schema.model_json_schema()["properties"]["allergens"]
    items = field["items"] if "items" in field else next(kind["items"] for kind in field["anyOf"] if "items" in kind)
    assert items["enum"] == THE_FOURTEEN



# A customer's allergy against what a dish contains


def test_a_dish_contains_those_of_the_allergy_it_declares_in_the_order_of_the_list():
    assert allergens.found_in(["milk", "fish", "gluten"], ["sesame", "gluten", "milk"]) == ["gluten", "milk"]


@pytest.mark.parametrize(("allergy", "dish"), [([], ["gluten"]), (["fish"], ["gluten"]), (["fish"], [])])
def test_a_dish_contains_none_of_an_allergy_it_does_not_declare(allergy, dish):
    assert allergens.found_in(allergy, dish) == []


def test_what_a_tool_reads_of_an_allergy_lists_the_fourteen_codes():
    properties = allergens.AllergyOut.model_json_schema()["properties"]
    assert [properties[name]["items"]["enum"] for name in ("allergy", "allergy_in_dish")] == [THE_FOURTEEN] * 2

# What a CSV cell says


def test_a_row_takes_its_allergens_cell_as_written_and_empty_by_default():
    assert Row().allergens == ""
    assert Row(allergens="Gluten, leche").allergens == "Gluten, leche"


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(
    "cell",
    ["Gluten, Leche", "gluten,milk", "LECHE , gluten", " Milk ,Gluten ,", "Leche, gluten, leche", "milk, Gluten"],
)
def test_a_cell_reads_the_names_in_spanish_or_english_in_any_case_and_in_any_order(cell, language):
    with translation.override(language):
        assert allergens.read_into(cell, {"sku": "BUR"}) == {"sku": "BUR", "allergens": ["gluten", "milk"]}


def test_a_cell_reads_the_names_with_or_without_accents_and_by_their_codes():
    fields = allergens.read_into("Crustaceos, sésamo, FRUTOS DE CASCARA, tree nuts, sulphites", {})
    assert fields == {"allergens": ["crustaceans", "tree_nuts", "sesame", "sulphites"]}
    assert allergens.read_into("tree_nuts, egg", {}) == {"allergens": ["egg", "tree_nuts"]}


@pytest.mark.parametrize("cell", ["", "   ", " , "])
def test_an_empty_cell_is_a_product_without_allergens(cell):
    assert allergens.read_into(cell, {"sku": "BUR"}) == {"sku": "BUR", "allergens": []}


@pytest.mark.parametrize(
    ("language", "reason"),
    [("en", "Allergen not recognized: marisco"), ("es", "Alérgeno no reconocido: marisco")],
)
def test_a_name_off_the_list_is_the_reason_its_row_fails(language, reason):
    with translation.override(language):
        assert allergens.read_into("Gluten,  marisco , Leche", {"sku": "BUR"}) == reason

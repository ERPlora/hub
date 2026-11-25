"""What the schemas of Taxes share: a page of a list, and that every field of every schema says what it is (they
are also the JSON Schema of the assistant's tools)."""

import inspect

from ninja import Schema

from apps.tax import schemas
from apps.tax.schemas.aliases import AliasPage
from apps.tax.schemas.categories import CategoryPage, CategoryRowOut
from apps.tax.schemas.fields import Page, PageIn
from apps.tax.schemas.rules import RulePage

from .schema_checks import invalid_fields


def schema_classes():
    return [
        value
        for module in vars(schemas).values()
        if inspect.ismodule(module)
        for value in vars(module).values()
        if inspect.isclass(value)
        and issubclass(value, Schema)
        and value.__module__.startswith(schemas.__name__)
    ]


def test_every_field_of_every_schema_has_a_description():
    undescribed = [
        f"{schema.__name__}.{name}"
        for schema in schema_classes()
        for name, info in schema.model_fields.items()
        if not (info.description or "").strip()
    ]
    assert schema_classes() and undescribed == []


def test_page_defaults_and_bounds():
    assert PageIn().model_dump() == {"limit": 50, "offset": 0}
    assert PageIn(limit=100).limit == 100
    assert invalid_fields(PageIn, limit=0) == {"limit"}
    assert invalid_fields(PageIn, limit=101) == {"limit"}
    assert invalid_fields(PageIn, offset=-1) == {"offset"}


def test_the_pages_are_the_generic_page():
    assert CategoryPage is Page[CategoryRowOut]
    for page in (CategoryPage, RulePage, AliasPage):
        assert list(page.model_fields) == ["rows", "total", "limit", "offset"]

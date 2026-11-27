"""Text searches ignore case and accents on both sides, and every substring search of the hub goes through them."""

import re
from pathlib import Path

from django.conf import settings

from base.models.locations import Location
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.text_search import contains_text

__all__ = ["in_business_a"]

#: A plain ``__icontains`` lookup in a ``Q``, a ``filter``/``exclude`` keyword or a key built in a string.
PLAIN_ICONTAINS = re.compile(r"__icontains\b")


def found(term, *fields):
    rows = Location.objects.filter(contains_text(term, *fields)).exclude(is_default=True)
    return sorted(rows.values_list("name", flat=True))


@HUB_DB
def test_a_term_without_accents_finds_a_name_with_them():
    Location.objects.create(name="Café con leche")
    Location.objects.create(name="Té verde")
    assert found("cafe", "name") == ["Café con leche"]
    assert found("te verde", "name") == ["Té verde"]


@HUB_DB
def test_a_term_with_accents_finds_a_name_without_them_ignoring_case():
    Location.objects.create(name="CAFE SOLO")
    Location.objects.create(name="Menu del dia")
    assert found("Café", "name") == ["CAFE SOLO"]
    assert found("MENÚ DEL DÍA", "name") == ["Menu del dia"]


@HUB_DB
def test_any_of_the_fields_may_contain_it_even_one_that_is_not_text():
    shop = Location.objects.create(name="Shop")
    Location.objects.create(name="Bar")
    assert found(str(shop.id)[-6:].upper(), "name", "id") == ["Shop"]
    assert found("bar", "name", "id") == ["Bar"]


@HUB_DB
def test_the_wildcards_of_like_are_searched_as_themselves():
    Location.objects.create(name="Bar 50%")
    Location.objects.create(name="Bar 500")
    assert found("50%", "name") == ["Bar 50%"]
    assert found("_", "name") == []


def test_no_substring_search_of_the_hub_distinguishes_accents():
    root = Path(settings.BASE_DIR)
    offenders = [
        f"{path.relative_to(root)}:{number}"
        for folder in ("apps", "base")
        for path in sorted((root / folder).rglob("*.py"))
        if not {"tests", "migrations"} & set(path.relative_to(root).parts)
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if PLAIN_ICONTAINS.search(line)
    ]
    assert offenders == [], "search text with base.text_search.contains_text, not __icontains"

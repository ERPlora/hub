"""base/catalog/verticals.py: ``known_verticals`` and ``template_apps`` derive the template of each
vertical. The last test runs them on the real modules: the check of CI.
"""

import pytest

from base.catalog.app_registry import build_registry
from base.catalog.verticals import known_verticals, template_apps
from base.tests.apps_on_disk import module


@pytest.fixture
def vertical_modules(tmp_path):
    return [
        module(tmp_path, "booking", verticals=["hair_salon"], requires=["customer"]),
        module(tmp_path, "customer", requires=["contact"]),
        module(tmp_path, "contact"),
        module(tmp_path, "sale", verticals=["restaurant", "hair_salon"]),
        module(tmp_path, "table", verticals=["restaurant"]),
        module(tmp_path, "base", kind="platform"),
    ]


def test_known_verticals_are_the_union_of_the_modules_verticals(vertical_modules):
    assert known_verticals(vertical_modules) == ["hair_salon", "restaurant"]


def test_a_template_has_the_modules_of_its_vertical_closed_by_requires(
    vertical_modules,
):
    assert template_apps("hair_salon", vertical_modules) == [
        "booking",
        "contact",
        "customer",
        "sale",
    ]
    assert template_apps("restaurant", vertical_modules) == ["sale", "table"]


def test_an_unknown_vertical_has_no_template(vertical_modules):
    with pytest.raises(ValueError, match="bakery"):
        template_apps("bakery", vertical_modules)


def test_the_real_verticals_derive_from_the_modules():
    assert known_verticals() == sorted(
        {v for entry in build_registry() for v in entry.verticals}
    )

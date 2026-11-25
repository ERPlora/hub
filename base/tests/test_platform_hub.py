"""ERPlora's own hub by its name (``base.platform_hub``): the one it goes by, and the one its row had before."""

from types import SimpleNamespace

import pytest
from django.conf import settings as deployed
from live.slugs import is_reserved_hub_slug

from base import platform_hub


def test_it_goes_by_erp_and_was_named_erplora():
    assert (deployed.PLATFORM_HUB_SLUG, deployed.PLATFORM_HUB_FORMER_SLUG) == ("erp", "erplora")


@pytest.mark.parametrize("name", ["PLATFORM_HUB_SLUG", "PLATFORM_HUB_FORMER_SLUG"])
def test_no_business_can_take_either_of_its_names(name):
    assert is_reserved_hub_slug(getattr(deployed, name))


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("erp", True),
        ("erplora", True),
        ("ERP", False),
        ("erp2", False),
        ("hubs", False),
        ("test", False),
        ("acme", False),
        ("", False),
    ],
)
def test_both_of_its_names_are_its_own_and_no_other_is(slug, expected):
    assert platform_hub.is_platform_slug(slug) is expected


def test_the_name_it_goes_by_follows_the_setting(settings):
    settings.PLATFORM_HUB_SLUG = "internal"
    assert platform_hub.is_platform_slug("internal")
    assert not platform_hub.is_platform_slug("erp")


@pytest.mark.parametrize("slug", ["erp", "acme", "bar-123"])
def test_a_hub_is_served_under_its_own_name_and_a_business_under_its_own(slug):
    assert platform_hub.validate_served_slug(slug) == slug


@pytest.mark.parametrize("slug", ["erplora", "test", "hub", "hubs", "www", "ERP", "demo", "demo-0000beef", "xn--bcher-kva"])
def test_no_other_reserved_name_is_served_nor_the_one_it_had_before(slug):
    with pytest.raises(ValueError):
        platform_hub.validate_served_slug(slug)


def test_a_demo_is_served_where_the_caller_allows_it():
    assert platform_hub.validate_served_slug("demo-0000beef", allow_demo=True) == "demo-0000beef"
    with pytest.raises(ValueError, match="^reserved$"):
        platform_hub.validate_served_slug("erplora", allow_demo=True)


@pytest.mark.parametrize(
    ("slug", "is_platform", "expected"),
    [("erp", True, True), ("acme", False, True), ("erp", False, False)],
    ids=["its own row", "a business", "another row under its name"],
)
def test_only_its_own_row_is_served_under_its_name(slug, is_platform, expected):
    assert platform_hub.may_be_served(SimpleNamespace(slug=slug, is_platform=is_platform)) is expected

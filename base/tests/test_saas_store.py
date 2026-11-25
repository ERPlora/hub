"""Where a business buys on erplora.com (``base.saas_store``): its plans and its Store."""

import uuid

import pytest

from base import saas_store

HUB_ID = uuid.UUID("0199a1b2-0000-7000-8000-000000000001")


@pytest.fixture(autouse=True)
def erplora_com(settings):
    settings.SAAS_URL = "https://erplora.com/"


def test_a_business_buys_in_the_plans_and_the_store_that_name_it():
    assert saas_store.plans_url("bar", HUB_ID) == f"https://erplora.com/dashboard/store/plans?business={HUB_ID}"
    assert saas_store.apps_url("bar", HUB_ID) == f"https://erplora.com/dashboard/store/modules?business={HUB_ID}"


def test_the_plans_go_without_naming_the_business_where_nobody_is_signed_in():
    assert saas_store.plans_url("bar") == "https://erplora.com/dashboard/store/plans"


@pytest.mark.parametrize("slug", ["erp", "erplora"])
def test_erplora_s_own_hub_has_nowhere_to_buy(slug):
    assert saas_store.plans_url(slug, HUB_ID) == ""
    assert saas_store.plans_url(slug) == ""
    assert saas_store.apps_url(slug, HUB_ID) == ""


@pytest.mark.parametrize("slug", ["erp-bar", "erploras", "er"])
def test_a_business_with_a_name_like_its_own_buys_as_any_other(slug):
    assert saas_store.plans_url(slug, HUB_ID).endswith(f"?business={HUB_ID}")
    assert saas_store.apps_url(slug, HUB_ID).endswith(f"?business={HUB_ID}")


def test_a_server_not_linked_to_erplora_com_has_nowhere_to_buy(settings):
    settings.SAAS_URL = ""

    assert (saas_store.plans_url("bar", HUB_ID), saas_store.apps_url("bar", HUB_ID)) == ("", "")

"""Which Host is which hub: the platform's host, the domain the hubs live under and the shortest slug."""

from django.conf import settings
from live.slugs import is_reserved_hub_slug

from config.tests.settings_env import DEVELOPMENT_ENV, PRODUCTION_ENV


def test_the_platform_host_is_hubs_and_no_customer_can_take_it():
    # hubs.erplora.com (locally hubs.localhost:8000) is only the Hub admin for the staff;
    # `hub` stays reserved but is not the platform host.
    assert settings.PLATFORM_HOST_LABEL == "hubs"
    assert is_reserved_hub_slug(settings.PLATFORM_HOST_LABEL)


def test_hub_base_domain_comes_from_the_environment(load_settings):
    # Production's hubs live under erplora.com, locally under localhost (a.localhost:8000).
    assert load_settings(**PRODUCTION_ENV)["HUB_BASE_DOMAIN"] == "erplora.com"
    assert load_settings(**DEVELOPMENT_ENV)["HUB_BASE_DOMAIN"] == "localhost"
    # pre: <slug>.pre.erplora.com and hubs.pre.erplora.com; written in any case, with dots around.
    loaded = load_settings(**PRODUCTION_ENV, HUB_BASE_DOMAIN=".Pre.Erplora.com.")
    assert loaded["HUB_BASE_DOMAIN"] == "pre.erplora.com"
    # Empty: no base domain, the hub is the Host's first label wherever it is.
    assert load_settings(**PRODUCTION_ENV, HUB_BASE_DOMAIN="")["HUB_BASE_DOMAIN"] == ""


def test_one_letter_hubs_only_in_local_development(load_settings):
    # The local demo hubs are a and b; production enforces live.slugs' minimum of 3.
    assert load_settings(**DEVELOPMENT_ENV)["LIVE"]["hub_slug_min_length"] == 1
    assert load_settings(**PRODUCTION_ENV)["LIVE"]["hub_slug_min_length"] == 3

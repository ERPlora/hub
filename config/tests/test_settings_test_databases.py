"""The test databases' names: from TEST_DB_NAME, and short enough for PostgreSQL whatever it says."""

import hashlib

import pytest

from config.tests.settings_env import DEVELOPMENT_ENV


def test_the_test_databases_are_named_by_the_environment(load_settings):
    # Two suites at once (two sessions, two checkouts) each pick their own TEST_DB_NAME: with one
    # fixed name the second run finds the database taken and drops or breaks the first's, as
    # saas-next's TEST_DB_NAME.
    databases = load_settings(**DEVELOPMENT_ENV, TEST_DB_NAME="test_hub_sup")[
        "DATABASES"
    ]
    assert databases["default"]["TEST"]["NAME"] == "test_hub_sup"
    assert databases["shared"]["TEST"]["NAME"] == "test_hub_sup_shared"


#: The fleet's recipe: ``test_hub_next_`` and up to 35 characters of its task's key, 49 in all.
LONG_TEST_DB_NAME = "test_hub_next_fix_hub_test_migrator_long_test_db_"
#: The same but for its last character: another session at the same time.
OTHER_LONG_TEST_DB_NAME = "test_hub_next_fix_hub_test_migrator_long_test_db2"
#: What pytest-django appends to every test database under pytest-xdist (``-n``): ``_gw<worker>``.
XDIST_SUFFIXES = ("", "_gw0", "_gw9", "_gw10", "_gw999")


def names_the_suite_derives(databases: dict) -> list[str]:
    """Every database the suite may create from these settings, with and without xdist's suffix: the test databases
    and, from control's, both test hubs', a demo's (``<control>_demo_<hex>``, the longest)
    and every template's (``base.tenancy.names``, which refuses a name past PostgreSQL's 63 characters instead of
    truncating it)."""
    from base import catalog
    from base.tenancy import names
    from base.tenancy.tests import hubs

    verticals = (None, hubs.TEMPLATE_VERTICAL, *catalog.verticals.known_verticals())
    derived = []
    for suffix in XDIST_SUFFIXES:
        control = databases["default"]["TEST"]["NAME"] + suffix
        derived += [control, *(databases[alias]["TEST"]["NAME"] + suffix for alias in ("shared", "hub_template"))]
        derived += [names.hub_db_name(control, hub_id) for hub_id in (hubs.HUB_A_ID, hubs.HUB_B_ID)]
        derived += [names.demo_db_name(control, hubs.HUB_A_ID)]
        derived += [names.template_db_name(control, vertical) for vertical in verticals]
    return derived


@pytest.mark.parametrize(
    "requested",
    # "ñ" * 10: 10 characters but 20 bytes, past the 19 that fit (PostgreSQL's limit counts bytes).
    ["test_hub_next", "test_hub_sup", "t" * 19, "t" * 20, LONG_TEST_DB_NAME, "t" * 63, "ñ" * 10, "ñ" * 40, "t" * 100],
)
def test_every_database_the_suite_derives_from_any_test_db_name_fits_in_postgres(load_settings, requested):
    """A worker never counts characters: whatever TEST_DB_NAME it sets, every name fits (hub#188, hub#204)."""
    from base.tenancy import names

    databases = load_settings(**DEVELOPMENT_ENV, TEST_DB_NAME=requested)["DATABASES"]

    too_long = [name for name in names_the_suite_derives(databases) if len(name.encode()) > names.MAX_IDENTIFIER]
    assert too_long == []


def test_a_test_db_name_that_fits_is_kept_as_it_is(load_settings):
    # --reuse-db and the fleet's sweep.sh find a short name's databases by that name.
    for requested in ("test_hub_next", "t" * 19):
        databases = load_settings(**DEVELOPMENT_ENV, TEST_DB_NAME=requested)["DATABASES"]
        assert databases["default"]["TEST"]["NAME"] == requested


def test_a_long_test_db_name_is_shortened_the_same_every_run_and_apart_from_another(load_settings):
    """Its first characters and the first 8 of its SHA-256 (the sweep recomputes it the same way in a shell): the same
    database every run (--reuse-db, the sweep) and another one for another name (two sessions at once)."""

    def test_names(requested: str) -> dict:
        databases = load_settings(**DEVELOPMENT_ENV, DB_NAME="pre_hub", TEST_DB_NAME=requested)["DATABASES"]
        assert (databases["default"]["NAME"], databases["hub_template"]["NAME"]) == ("pre_hub", "pre_hub_template")
        return {alias: databases[alias]["TEST"]["NAME"] for alias in ("default", "shared", "hub_template")}

    # 19 characters fit (a demo's ``_demo_<hex>`` and xdist's ``_gw999`` after them): its first 10, ``_`` and 8.
    shortened = f"test_hub_n_{hashlib.sha256(LONG_TEST_DB_NAME.encode()).hexdigest()[:8]}"
    assert test_names(LONG_TEST_DB_NAME) == {
        "default": shortened,
        "shared": f"{shortened}_shared",
        "hub_template": f"{shortened}_template",
    }
    assert test_names(OTHER_LONG_TEST_DB_NAME)["default"] not in (shortened, OTHER_LONG_TEST_DB_NAME)

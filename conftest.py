"""Fixtures shared by every hub-next test."""

import json

import pytest
from django.utils import translation

from config import testing

ENTRY = "frontend/main.ts"


# Fails the test that leaves a database connection with a session setting changed (config/testing.py).
session_settings_left_as_found = pytest.fixture(autouse=True)(testing.session_settings_left_as_found)


@pytest.fixture(autouse=True)
def default_language():
    """Every test starts and ends in the default language (``settings.LANGUAGE_CODE``).

    A request of the test client goes through ``LocaleMiddleware``, which activates the browser's language in the
    thread and never deactivates it, so a request in Spanish would leave Spanish to the next tests of the same
    worker (base/tests/test_language_isolation.py). Resetting before covers what a fixture wider than the test
    left; resetting after, the module and session fixtures set up before the next test's own. A test that wants
    another language says so in its body or a function fixture (``translation.override("es")``).
    """
    translation.deactivate()
    yield
    translation.deactivate()


@pytest.fixture(autouse=True)
def cache_cleared():
    """Every test starts and ends with an empty cache (the process's memory in the tests).

    The doors count refused attempts per caller in the cache (``base.throttle.AttemptLimit``) and every test client
    calls from the same address: without this, the failures of earlier tests of the same worker would refuse a later
    test's first attempt."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


#: The hubs every test that uses the database finds in the registry, as ``manage.py seed_local_hubs`` leaves them.
LOCAL_HUBS = ("a", "b")


@pytest.fixture(autouse=True)
def local_hubs(request):
    """The local hubs ``a`` and ``b``, ready, in the registry (``base.Hub``) of every test that uses the database.

    The host gate (``base.middleware``) answers 404 to a slug without a row, so a test on ``a.localhost`` needs it,
    as the developer's database has it after ``seed_local_hubs``. A test without the database gets nothing (and a
    test without it that asks ``a.localhost`` for a hub's page fails: it must say ``django_db``).
    """
    marked = request.node.get_closest_marker("django_db") is not None
    if not (marked or {"db", "transactional_db"} & set(request.fixturenames)):
        return
    request.getfixturevalue("transactional_db" if "transactional_db" in request.fixturenames else "db")
    from base.models import Hub

    for slug in LOCAL_HUBS:
        Hub.objects.get_or_create(slug=slug, defaults={"status": Hub.Status.READY})


@pytest.fixture
def spa_manifest(settings, tmp_path):
    """A Vite build manifest for the SPA entry, as `vite build` writes it."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                ENTRY: {
                    "file": "assets/main-abc123.js",
                    "src": ENTRY,
                    "isEntry": True,
                    "css": ["assets/main-def456.css"],
                    "imports": ["_vendor-789.js"],
                },
                "_vendor-789.js": {"file": "assets/vendor-789.js"},
            }
        )
    )
    settings.LIVE = {**settings.LIVE, "spa": {**settings.LIVE["spa"], "manifest": manifest}}
    return manifest


# ── Phase 2's tenancy (plan docs/plans/2026-10-22-fase-2-tenencia.md, S1) ─────────────────────────────────────────


@pytest.fixture(autouse=True, scope="session")
def shared_database_fallback():
    """The tests written before the tenancy run on phase 1's shared database without a context of their own.

    In production a hub's model or operation without ``use_hub`` fails (``HubContextMissing``). The suite's tests call
    operations and the ORM directly, in their own threads too, as phase 1 let them: here they fall back on the shared
    database (``default``), as the hubs ``a`` and ``b`` do (``db_name=""``). The tenancy's own tests turn it off
    (``no_test_fallback``, ``base/tenancy/tests/conftest.py``) and so do the ones of every way in (requests, the live
    executor, the print socket, ``/internal``, the worker, the commands), which must open their context themselves.
    """
    from base.tenancy import context

    context._test_fallback = context.SHARED_DATABASE
    yield
    context._test_fallback = None


@pytest.fixture(scope="session")
def hub_databases(django_db_setup, django_db_blocker):
    """The template and the two hubs' databases of this session (``base/tenancy/tests/hubs.py``), dropped at its end."""
    from base.tenancy.tests import hubs

    with django_db_blocker.unblock():
        built = hubs.build()
    yield built
    with django_db_blocker.unblock():
        hubs.drop(built)


def _hub_with_its_database(request, hub_id, slug, db_name):
    """The row in control of a hub whose database the session made; the test names it in its ``django_db``
    (``databases=hubs.HUB_DATABASES``), whose transaction rolls both back. A ``transaction=True`` test commits in
    the hub's database: its rows are deleted after it."""
    from base.tenancy.tests import hubs
    from control.models import Hub

    hub = Hub.objects.create(id=hub_id, slug=slug, status=Hub.Status.READY, db_name=db_name)
    yield hub
    marker = request.node.get_closest_marker("django_db")
    if marker is not None and marker.kwargs.get("transaction"):
        hubs.empty(db_name)


@pytest.fixture
def hub_a(request, hub_databases):
    """The hub ``tenant-a``, ready, with its own database (``hub_databases.a``): what a hub of phase 2 is."""
    from base.tenancy.tests import hubs

    yield from _hub_with_its_database(request, hubs.HUB_A_ID, "tenant-a", hub_databases.a)


@pytest.fixture
def hub_b(request, hub_databases):
    """The hub ``tenant-b``, ready, with its own database (``hub_databases.b``)."""
    from base.tenancy.tests import hubs

    yield from _hub_with_its_database(request, hubs.HUB_B_ID, "tenant-b", hub_databases.b)


@pytest.fixture(autouse=True)
def hub_aliases_forgotten():
    """Every alias a test registers (``use_hub``, the migrator) is closed and forgotten after it, so the next test
    case starts from the settings' own aliases (``base/tenancy/tests/hubs.py``, ``forget_aliases``)."""
    from django.db import connections

    from base.tenancy.tests import hubs

    before = connections.settings
    yield
    hubs.forget_aliases(before)



"""Locations (round 2026-10-24b, multi-location): a hub is one business, with its tax id and one database, and the
places it works in live inside it, as Square, Shopify, Lightspeed and Odoo keep several shops in one company.

Every hub's database is born with exactly one default location, «Main» (``base/migrations/0015_location``; a new
hub inherits it from the template it is cloned from), which the reader sees in their language («Principal» in
Spanish). At most one is the default and the default is always active. ``base.location.list`` reads them for everyone
of the hub, over ``GET /api/locations`` only: it becomes a live query with the commands that write them. Nothing writes
them yet but the Django admin of the platform host, where which one is the default is read only and the default is
never deleted. One hub never sees another's.
"""

from importlib import import_module

import pytest
from django.contrib import admin
from django.db import IntegrityError, connection, transaction
from django.db.migrations.operations import RunPython
from django.urls import resolve
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.operations import get

from base.admin import LocationAdmin
from base.models import DEFAULT_LOCATION_NAME, Location
from base.schemas import LocationListIn
from base.tenancy import context, inventory
from base.tenancy.tests import hubs

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
HOME = "base.view_home"
PLATFORM = "hubs.localhost:8000"
HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)
#: base/tests/test_api.py's map of the SPA's routes takes these too.
LOCATION_ROUTES = {("GET", "/locations", "base.location.list")}


def listed(scope=A, language="en", permissions=(HOME,)) -> list[dict]:
    ctx = OperationContext(scope=scope, actor="ana", permissions=frozenset(permissions), language=language)
    with translation.override(language):
        return get("base.location.list")(ctx, LocationListIn()).model_dump(mode="json")["locations"]


def default_location() -> Location:
    return Location.objects.get(is_default=True)


# ── The model ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_location_lives_in_each_hubs_database():
    assert inventory.classify(Location) == inventory.HUB


def test_its_key_is_a_uuid7():
    assert Location.objects.create(name="Calle Mayor").id.version == 7


def test_every_database_is_born_with_one_default_location_called_main():
    [main] = Location.objects.filter(is_default=True)
    assert (main.name, main.is_active) == ("Main", True)
    assert DEFAULT_LOCATION_NAME == "Main"


def test_more_places_than_the_default_may_be_added_and_none_of_them_is_the_default():
    Location.objects.create(name="Calle Mayor")
    Location.objects.create(name="Puerto")

    assert Location.objects.filter(is_default=False).count() == 2
    assert Location.objects.filter(is_default=True).count() == 1


def test_a_second_default_is_refused_by_the_database():
    with pytest.raises(IntegrityError), transaction.atomic():
        Location.objects.create(name="Calle Mayor", is_default=True)


def test_the_default_is_never_inactive():
    with pytest.raises(IntegrityError), transaction.atomic():
        Location.objects.filter(is_default=True).update(is_active=False)


def test_another_location_may_be_inactive():
    Location.objects.create(name="Puerto", is_active=False)

    assert Location.objects.get(name="Puerto").is_active is False


def test_the_default_reads_main_in_the_readers_language():
    main = default_location()

    with translation.override("es"):
        assert (main.display_name, str(main)) == ("Principal", "Principal")
    with translation.override("en"):
        assert main.display_name == "Main"


def test_a_renamed_default_and_any_other_keep_the_name_they_were_given():
    Location.objects.filter(is_default=True).update(name="Calle Mayor")
    other = Location.objects.create(name="Main")

    with translation.override("es"):
        assert default_location().display_name == "Calle Mayor"
        assert other.display_name == "Main"


def test_its_words_are_translated():
    with translation.override("es"):
        assert str(Location._meta.verbose_name) == "ubicación"
        assert str(Location._meta.verbose_name_plural) == "ubicaciones"
        labels = {field.name: str(field.verbose_name) for field in Location._meta.fields if field.name != "id"}
    assert labels == {
        "name": "nombre",
        "is_default": "por defecto",
        "is_active": "activa",
        "created_at": "creada el",
    }


# ── The migration ──────────────────────────────────────────────────────────────────────────────────────────────────


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _migration():
    return import_module("base.migrations.0015_location")


def _apps():
    from django.apps import apps

    return apps


def test_the_migration_plants_main_once_and_its_reverse_takes_it_away():
    migration = _migration()
    Location.objects.all().delete()

    migration.plant_main(_apps(), _SchemaEditor())
    migration.plant_main(_apps(), _SchemaEditor())
    [main] = Location.objects.all()
    assert (main.name, main.is_default, main.is_active, main.id.version) == ("Main", True, True, 7)

    migration.uproot_main(_apps(), _SchemaEditor())
    assert not Location.objects.exists()


def test_the_migration_leaves_a_default_the_business_already_has():
    migration = _migration()
    Location.objects.filter(is_default=True).update(name="Calle Mayor")

    migration.plant_main(_apps(), _SchemaEditor())

    assert list(Location.objects.values_list("name", "is_default")) == [("Calle Mayor", True)]


def test_the_reverse_leaves_the_places_the_business_added():
    migration = _migration()
    Location.objects.create(name="Puerto")

    migration.uproot_main(_apps(), _SchemaEditor())

    assert list(Location.objects.values_list("name", flat=True)) == ["Puerto"]


def test_every_step_of_the_migration_goes_back():
    steps = _migration().Migration.operations

    assert [type(step).__name__ for step in steps] == ["CreateModel", "RunPython"]
    assert all(step.reversible for step in steps if isinstance(step, RunPython))


# ── A hub with a database of its own (phase 2) ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def no_test_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database."""
    monkeypatch.setattr(context, "_test_fallback", None)


def _hub_scope(hub) -> Scope:
    return Scope("host", hub.slug)


@HUB_DB
def test_a_new_hubs_database_has_exactly_one_default_location(hub_a, hub_b, no_test_fallback):
    for hub in (hub_a, hub_b):
        with context.use_hub(hub):
            assert list(Location.objects.filter(is_default=True).values_list("name", "is_active")) == [("Main", True)]


@HUB_DB
def test_without_a_hub_a_location_is_never_read_from_control(no_test_fallback):
    with pytest.raises(context.HubContextMissing):
        Location.objects.count()


@HUB_DB
def test_one_hub_never_lists_anothers_locations(hub_a, hub_b, no_test_fallback):
    with context.use_hub(hub_b):
        Location.objects.create(name="Puerto de B")

    with context.use_hub(hub_a):
        of_a = listed(_hub_scope(hub_a))
    with context.use_hub(hub_b):
        of_b = listed(_hub_scope(hub_b))

    assert [row["name"] for row in of_a] == ["Main"]
    assert [row["name"] for row in of_b] == ["Main", "Puerto de B"]


# ── base.location.list ─────────────────────────────────────────────────────────────────────────────────────────────


def test_everyone_of_the_hub_lists_its_locations_the_default_first():
    Location.objects.create(name="Zaragoza")
    Location.objects.create(name="Bilbao", is_active=False)
    main = default_location()

    rows = listed(language="es")

    assert rows[0] == {"id": str(main.id), "name": "Principal", "is_default": True, "is_active": True}
    assert [(row["name"], row["is_default"], row["is_active"]) for row in rows[1:]] == [
        ("Bilbao", False, False),
        ("Zaragoza", False, True),
    ]


def test_without_the_homes_permission_nothing_is_listed():
    with pytest.raises(PermissionDenied):
        listed(permissions=())


def test_it_is_a_read_that_tells_the_assistant_what_it_does():
    op = get("base.location.list")

    assert (op.kind, op.permission) == ("query", HOME)
    assert isinstance(op.ai, dict) and op.ai["description"].strip()


def test_it_is_bound_to_its_route():
    from base.api import router

    [route] = router.path_operations["/locations"].operations
    assert (route.methods, route.operation_id) == (["GET"], "base.location.list")
    assert resolve("/api/locations").url_name


def test_an_employee_reads_them_over_http_and_a_stranger_does_not(client, make_user):
    assert client.get("/api/locations", HTTP_HOST="a.localhost:8000").status_code in (401, 403)

    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = client.get("/api/locations", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT_LANGUAGE="es")

    assert response.status_code == 200, response.content
    assert [row["name"] for row in response.json()["locations"]] == ["Principal"]


def test_it_is_not_live_until_something_writes_a_location():
    # It becomes a live query with the base.location.* commands and their events; no other event changes a location.
    assert not live_registry.is_subscribable("base.location.list")


# ── The Django admin (platform host) ───────────────────────────────────────────────────────────────────────────────


def test_it_is_registered_in_the_admin():
    assert isinstance(admin.site._registry[Location], LocationAdmin)


def test_the_admin_lists_the_locations(client, superuser):
    client.force_login(superuser)

    html = client.get("/admin/base/location/", HTTP_HOST=PLATFORM).content.decode()

    assert "Main" in html


def test_a_place_added_by_hand_is_never_the_default(client, superuser):
    client.force_login(superuser)

    response = client.post(
        "/admin/base/location/add/", {"name": "Calle Mayor", "is_active": "on", "is_default": "on"}, HTTP_HOST=PLATFORM
    )

    assert response.status_code == 302, response.content
    assert Location.objects.get(name="Calle Mayor").is_default is False
    assert Location.objects.filter(is_default=True).count() == 1


def test_the_default_is_renamed_by_hand_but_stays_the_default_and_active(client, superuser):
    client.force_login(superuser)
    main = default_location()

    # An unchecked box sends nothing: «is_active» off, «is_default» off.
    response = client.post(f"/admin/base/location/{main.pk}/change/", {"name": "Calle Mayor"}, HTTP_HOST=PLATFORM)

    assert response.status_code == 302, response.content
    main.refresh_from_db()
    assert (main.name, main.is_default, main.is_active) == ("Calle Mayor", True, True)


def test_another_place_is_turned_off_by_hand(client, superuser):
    client.force_login(superuser)
    other = Location.objects.create(name="Puerto")

    response = client.post(f"/admin/base/location/{other.pk}/change/", {"name": "Puerto"}, HTTP_HOST=PLATFORM)

    assert response.status_code == 302, response.content
    other.refresh_from_db()
    assert other.is_active is False


def test_the_default_is_never_deleted_by_hand(client, superuser):
    client.force_login(superuser)
    main = default_location()

    assert client.get(f"/admin/base/location/{main.pk}/delete/", HTTP_HOST=PLATFORM).status_code == 403
    answer = client.post(f"/admin/base/location/{main.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM)
    assert answer.status_code == 403
    assert Location.objects.filter(pk=main.pk).exists()


def test_nor_with_the_others_from_the_list(client, superuser):
    client.force_login(superuser)
    main = default_location()
    other = Location.objects.create(name="Puerto")

    response = client.post(
        "/admin/base/location/",
        {"action": "delete_selected", "_selected_action": [str(main.pk), str(other.pk)], "post": "yes"},
        HTTP_HOST=PLATFORM,
    )

    assert response.status_code == 403
    assert set(Location.objects.values_list("name", flat=True)) == {"Main", "Puerto"}


def test_another_place_is_deleted_by_hand(client, superuser):
    client.force_login(superuser)
    other = Location.objects.create(name="Puerto")

    response = client.post(f"/admin/base/location/{other.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM)

    assert response.status_code == 302
    assert not Location.objects.filter(pk=other.pk).exists()

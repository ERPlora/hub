"""Settings › Data, the reads (PLAN-HUB round 2026-10-21, «Blueprints»): the catalogue, what a blueprint brings, the
export, the loads and the apps' data.

``base.blueprint.list`` (BASE-G103, the Home's card BASE-G131) gives the seeds of the catalogue, the hub's country
first and then the person's language, and whether the business has nothing a template brings yet;
``base.blueprint.inspect`` (BASE-G104, BASE-G105) what a template or a file brings, writing nothing;
``base.blueprint.export`` (BASE-G101, BASE-G102) the ``.blueprint.zip`` of the apps and datasets chosen, a template
never with personal data; ``base.import.list`` (BASE-G107, BASE-G108) the loads, the last one that did not go in whole
first; ``base.dataset.list`` (BASE-G102) every app on with what of it can travel and how many rows it has. Only who runs
the hub reads them.
"""

import base64
import io
import json
import zipfile

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.operations import get

from base import blueprint
from base.models import AppActivation, Hub, ImportBatch, Membership
from base.permissions import permissions_for

pytestmark = pytest.mark.django_db

A = Scope("host", "a")


def person(role, username="olga", language="es"):
    user = get_user_model().objects.create_user(username=username, password="pw")
    Membership.objects.create(user=user, host="a", role=role)
    return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language=language)


@pytest.fixture
def owner():
    return person(Membership.Role.OWNER)


@pytest.fixture
def manager():
    return person(Membership.Role.MANAGER, "mario")


def call(ctx, operation, /, **data):
    op = get(operation)
    return op(ctx, op.input(**data))


def a_file(purpose="backup", apps=("table", "customer"), data=None):
    bundle = blueprint.Bundle(
        manifest=blueprint.manifest(
            name="Copia del Bar Pepe",
            language="es",
            country="ES",
            purpose=purpose,
            created_at="2026-10-24T10:00:00+00:00",
            vertical="restaurant",
            apps=list(apps),
        ),
        data=data
        or {
            "table.zone": [{"name": "Patio", "description": "", "color": "warning", "sort_order": 1}],
            "customer.customer": [{"name": "Lucía Pérez", "email": "lucia@example.com", "phone": ""}],
        },
    )
    return base64.b64encode(blueprint.write_zip(bundle)).decode()


# ── The catalogue (BASE-G103, BASE-G131) ───────────────────────────────────────────────────────────────────────────


def test_the_catalogue_puts_the_persons_language_first():
    spanish = call(person(Membership.Role.OWNER, "olga", "es"), "base.blueprint.list")
    english = call(person(Membership.Role.OWNER, "otto", "en"), "base.blueprint.list")

    assert [template.key for template in spanish.templates] == ["hair_salon.es", "restaurant.es", "hair_salon.en", "restaurant.en"]
    assert [template.key for template in english.templates][:2] == ["hair_salon.en", "restaurant.en"]


def test_the_hubs_country_goes_before_the_language(owner, monkeypatch):
    seeds = blueprint.catalog()
    french = blueprint.Template(**{**seeds[0].__dict__, "key": "restaurant.fr", "language": "fr", "country": "FR"})
    monkeypatch.setattr(blueprint, "catalog", lambda: [*seeds, french])
    Hub.objects.filter(slug="a").update(country="FR")

    listed = call(owner, "base.blueprint.list")

    assert listed.templates[0].key == "restaurant.fr"


def test_within_its_language_the_hubs_own_vertical_comes_first(owner):
    Hub.objects.filter(slug="a").update(vertical="restaurant")

    keys = [template.key for template in call(owner, "base.blueprint.list").templates]

    assert keys == ["restaurant.es", "hair_salon.es", "restaurant.en", "hair_salon.en"]


def test_a_template_says_what_it_brings_by_name(owner):
    restaurant = next(template for template in call(owner, "base.blueprint.list").templates if template.key == "restaurant.es")

    assert (restaurant.name, restaurant.language, restaurant.country, restaurant.version) == ("Restaurante", "es", "ES", "1")
    assert {(part.key, part.label, part.rows) for part in restaurant.contents} == {
        ("inventory.category", "Categorías de productos", 6),
        ("inventory.product", "Productos", 16),
        ("table.zone", "Zonas", 2),
        ("table.table", "Mesas", 10),
    }
    assert "Mesas" in [app.label for app in restaurant.apps]


def test_an_empty_business_is_told_so_until_something_is_loaded(owner):
    assert call(owner, "base.blueprint.list").empty is True

    call(owner, "base.blueprint.import", template="hair_salon.es")

    assert call(owner, "base.blueprint.list").empty is False


C = Scope("host", "c")


@pytest.fixture
def born():
    """A business as it is born (round 2026-10-27): ready in the registry, every app off (no row), and its owner."""
    Hub.objects.create(slug="c", status=Hub.Status.READY)
    user = get_user_model().objects.create_user(username="carla", password="pw")
    Membership.objects.create(user=user, host="c", role=Membership.Role.OWNER)
    return OperationContext(scope=C, actor=user, permissions=permissions_for(user, C), language="es")


def test_a_business_born_with_every_app_off_is_empty_for_the_homes_card(born):
    """Nothing on, nothing to count: the Home offers a template to a business just born."""
    listed = call(born, "base.blueprint.list")
    assert listed.empty is True
    assert listed.templates


def test_who_does_not_run_the_hub_does_not_get_the_catalogue(manager):
    with pytest.raises(PermissionDenied):
        call(manager, "base.blueprint.list")


# ── What a blueprint brings (BASE-G104, BASE-G105) ─────────────────────────────────────────────────────────────────


def test_inspecting_a_template_says_its_apps_and_rows_and_writes_nothing(owner):
    summary = call(owner, "base.blueprint.inspect", template="hair_salon.es")

    assert (summary.name, summary.source, summary.purpose, summary.version) == ("Peluquería", "catalog", "template", "1")
    service = next(app for app in summary.apps if app.id == "service")
    assert (service.label, service.status) == ("Servicios", "on")
    assert [(part.key, part.rows, part.travels) for part in service.datasets] == [
        ("service.category", 4, True),
        ("service.service", 8, True),
    ]
    assert call(owner, "service.service.list", limit=1).total == 0


def test_inspecting_a_file_says_what_it_brings_and_what_never_travels(owner):
    summary = call(owner, "base.blueprint.inspect", file_base64=a_file(purpose="template"))

    assert (summary.name, summary.source, summary.purpose) == ("Copia del Bar Pepe", "file", "template")
    customer = next(app for app in summary.apps if app.id == "customer")
    assert [(part.key, part.travels) for part in customer.datasets] == [("customer.customer", False)]
    backup = call(owner, "base.blueprint.inspect", file_base64=a_file(purpose="backup"))
    assert [part.travels for app in backup.apps for part in app.datasets] == [True, True]


def test_an_app_off_the_blueprint_lists_is_said_to_turn_on_and_one_it_does_not_list_stays_off(born):
    """The load turns on the apps its manifest lists (round 2026-10-27); an app named only by its data is not."""
    summary = call(born, "base.blueprint.inspect", file_base64=a_file(apps=("table",)))

    assert {app.id: app.status for app in summary.apps} == {"table": "turns_on", "customer": "inactive"}
    assert not AppActivation.objects.filter(host="c").exists()


def test_an_app_the_hub_does_not_have_is_said(owner):
    summary = call(owner, "base.blueprint.inspect", file_base64=a_file(apps=("table", "bakery_oven")))

    assert {app.id: app.status for app in summary.apps}["bakery_oven"] == "unknown"


def test_inspecting_a_broken_file_says_why(owner):
    with pytest.raises(InvalidPayload) as refused:
        call(owner, "base.blueprint.inspect", file_base64=base64.b64encode(b"hello").decode())
    assert refused.value.code == "base.blueprint_invalid"
    with pytest.raises(NotFound):
        call(owner, "base.blueprint.inspect", template="bakery.es")


# ── Export (BASE-G101, BASE-G102) ──────────────────────────────────────────────────────────────────────────────────


def opened(exported):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(exported.content_base64)))
    return {name: json.loads(archive.read(name)) for name in archive.namelist()}


def test_exporting_a_template_writes_the_apps_chosen_without_personal_data(owner):
    Hub.objects.filter(slug="a").update(country="ES", vertical="restaurant")
    call(owner, "base.blueprint.import", template="restaurant.es")
    call(owner, "customer.customer.create", name="Lucía Pérez", email="lucia@example.com")

    exported = call(
        owner,
        "base.blueprint.export",
        name="Bar Pepe",
        language="es",
        purpose="template",
        apps=["inventory", "table", "customer"],
        data=["inventory", "customer"],
    )

    files = opened(exported)
    assert exported.filename == "bar-pepe_es.blueprint.zip"
    assert exported.content_type == "application/zip"
    assert sorted(files) == ["data/inventory.category.json", "data/inventory.product.json", "manifest.json"]
    manifest = files["manifest.json"]
    assert (manifest["name"], manifest["purpose"], manifest["country"], manifest["vertical"]) == ("Bar Pepe", "template", "ES", "restaurant")
    assert manifest["apps"] == ["inventory", "table", "customer"]
    assert len(files["data/inventory.product.json"]) == 16


def test_a_backup_takes_the_customers_and_the_datasets_chosen(owner):
    call(owner, "base.blueprint.import", template="restaurant.es")
    call(owner, "customer.customer.create", name="Lucía Pérez", email="lucia@example.com")

    exported = call(
        owner,
        "base.blueprint.export",
        name="Copia",
        language="es",
        purpose="backup",
        apps=["inventory", "customer"],
        data=["inventory", "customer"],
        datasets=["inventory.category"],  # of inventory, its categories only; of customer, every dataset
    )

    files = opened(exported)
    assert sorted(files) == ["data/customer.customer.json", "data/inventory.category.json", "manifest.json"]
    assert [row["name"] for row in files["data/customer.customer.json"]] == ["Lucía Pérez"]


@pytest.mark.parametrize(
    ("chosen", "field"),
    [
        ({"apps": ["bakery_oven"], "data": ["bakery_oven"]}, "apps"),
        ({"apps": ["base"]}, "apps"),
        ({"apps": ["table"], "data": ["inventory"]}, "data"),
        ({"apps": ["inventory"], "data": ["inventory"], "datasets": ["table.table"]}, "datasets"),
    ],
)
def test_an_export_of_something_the_hub_does_not_have_is_refused(owner, chosen, field):
    with pytest.raises(InvalidPayload) as refused:
        call(owner, "base.blueprint.export", name="Copia", language="es", purpose="backup", **chosen)
    assert list(refused.value.fields) == [field]


def test_who_does_not_run_the_hub_cannot_export(manager):
    with pytest.raises(PermissionDenied):
        call(manager, "base.blueprint.export", name="Copia", language="es", purpose="template", apps=[])


# ── The loads (BASE-G107, BASE-G108) ───────────────────────────────────────────────────────────────────────────────


def test_the_loads_come_newest_first_and_the_last_unfinished_one_is_offered_again(owner, monkeypatch):
    whole = call(owner, "base.blueprint.import", template="hair_salon.es")
    with monkeypatch.context() as patch:
        patch.setattr(blueprint, "active_apps", lambda scope: frozenset({"inventory"}))
        partial = call(owner, "base.blueprint.import", template="restaurant.es", apps=["inventory", "table"])

    loads = call(owner, "base.import.list")

    assert [load.id for load in loads.imports] == [partial.id, whole.id]
    assert loads.unfinished.id == partial.id
    assert (loads.unfinished.retry, loads.unfinished.retry_blocked) == (True, "")
    assert [load.undoable for load in loads.imports] == [True, True]


def test_a_load_that_went_in_whole_is_not_offered_again(owner):
    call(owner, "base.blueprint.import", template="hair_salon.es")

    assert call(owner, "base.import.list").unfinished is None


def test_an_unfinished_load_from_a_file_says_why_it_is_not_retried(owner):
    call(owner, "base.blueprint.import", file_base64=a_file(data={"table.table": [{"number": "1", "zone": "Nowhere"}]}))

    unfinished = call(owner, "base.import.list").unfinished

    assert (unfinished.retry, unfinished.retry_blocked) == (False, "file")


def test_an_undone_load_is_no_longer_offered_nor_undoable(owner, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(blueprint, "active_apps", lambda scope: frozenset({"inventory"}))
        partial = call(owner, "base.blueprint.import", template="restaurant.es", apps=["inventory", "table"])
    call(owner, "base.import.undo", id=partial.id)

    loads = call(owner, "base.import.list")

    assert loads.unfinished is None
    assert [load.undoable for load in loads.imports] == [False]


def test_the_loads_are_for_who_runs_the_hub(manager):
    with pytest.raises(PermissionDenied):
        call(manager, "base.import.list")


# ── The apps' data (BASE-G102) ─────────────────────────────────────────────────────────────────────────────────────


def test_every_app_on_is_listed_with_what_of_it_travels_and_how_many_rows(owner):
    call(owner, "base.blueprint.import", template="restaurant.es")

    apps = {app.id: app for app in call(owner, "base.dataset.list").apps}

    assert [(part.key, part.label, part.rows, part.personal) for part in apps["inventory"].datasets] == [
        ("inventory.category", "Categorías de productos", 6, False),
        ("inventory.product", "Productos", 16, False),
    ]
    assert [(part.key, part.personal) for part in apps["customer"].datasets] == [("customer.customer", True)]
    assert apps["sale"].datasets == []  # on, registered by an export, with nothing of its own that travels
    assert "base" not in apps
    assert list(apps) == sorted(apps, key=lambda app: apps[app].label)


def test_the_apps_data_is_for_who_runs_the_hub(manager):
    with pytest.raises(PermissionDenied):
        call(manager, "base.dataset.list")


def test_a_load_kept_in_phase_1_has_no_hub_column():
    assert "hub_id" not in {field.attname for field in ImportBatch._meta.get_fields() if hasattr(field, "attname")}

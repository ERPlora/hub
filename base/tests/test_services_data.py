"""Settings › Data, the writes (PLAN-HUB round 2026-10-21, «Blueprints»): load a blueprint, undo a load, reset.

``base.blueprint.import`` (BASE-G103–G107) loads a template of the catalogue or a ``.blueprint.zip`` and keeps its
report and the rows it created as an ``ImportBatch``; a load that did not go in whole is retried from the same
template version (never from an uploaded file). ``base.import.undo`` (BASE-G108) removes exactly the rows of one
load. ``base.hub.reset`` (BASE-G109) gives the plan of what each app would lose (``dry_run``) and, typed the
business's name, removes it; in phase 1 the business's data shares one database with every other hub, so the reset
is refused until the hub has its own (plan 2026-10-22-fase-2-tenencia, S5). Each one only for who runs the hub.
"""

import base64

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from base import activation, blueprint, events as base_events, relay, services
from base.catalog import template_apps
from base.models import AppActivation, Hub, ImportBatch, Membership
from base.permissions import permissions_for

pytestmark = pytest.mark.django_db

A = Scope("host", "a")


def person(role, username="olga"):
    user = get_user_model().objects.create_user(username=username, password="pw")
    Membership.objects.create(user=user, host="a", role=role)
    return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language="es")


@pytest.fixture
def owner():
    return person(Membership.Role.OWNER)


@pytest.fixture
def manager():
    return person(Membership.Role.MANAGER, "mario")


def call(ctx, operation, /, **data):
    op = get(operation)
    return op(ctx, op.input(**data))


def total(ctx, operation):
    return call(ctx, operation, limit=1).total


def events(name):
    return list(OutboxEvent.objects.filter(name=name, scope_key="a").values_list("payload", flat=True))


def a_file(purpose="template", data=None, apps=("table",)):
    bundle = blueprint.Bundle(
        manifest=blueprint.manifest(
            name="Bar Pepe",
            language="es",
            country="ES",
            purpose=purpose,
            created_at="2026-10-24T10:00:00+00:00",
            vertical="restaurant",
            apps=list(apps),
        ),
        data=data or {"table.zone": [{"name": "Patio", "description": "", "color": "warning", "sort_order": 1}]},
    )
    return base64.b64encode(blueprint.write_zip(bundle)).decode()


# ── Load a template of the catalogue (BASE-G103, BASE-G105, BASE-G106) ─────────────────────────────────────────────


def test_an_administrator_loads_a_template_and_keeps_its_report(owner):
    loaded = call(owner, "base.blueprint.import", template="restaurant.es")

    batch = ImportBatch.objects.get(pk=loaded.id)
    assert (loaded.name, loaded.source, loaded.status) == ("Restaurante", "catalog", "complete")
    assert (batch.template_key, batch.template_version, batch.undone_at) == ("restaurant.es", "1", None)
    assert loaded.rows == 34  # 6 categories, 16 products, 2 zones, 10 tables
    assert sum(len(ids) for ids in batch.created_rows.values()) == 34
    assert total(owner, "inventory.product.list") == 16
    inventory = next(app for app in loaded.report.apps if app.id == "inventory")
    assert (inventory.label, inventory.status) == ("Inventario", "applied")
    assert events("base.blueprint.imported") == [{"id": str(batch.pk), "status": "complete"}]


def test_the_report_is_in_the_persons_language(owner):
    english = OperationContext(scope=A, actor=owner.actor, permissions=owner.permissions, language="en")

    loaded = call(english, "base.blueprint.import", template="restaurant.en")

    inventory = next(app for app in loaded.report.apps if app.id == "inventory")
    assert inventory.label == "Inventory"
    assert [dataset.label for dataset in inventory.datasets] == ["Product categories", "Products"]


def test_who_does_not_run_the_hub_cannot_load_a_blueprint(manager):
    with pytest.raises(PermissionDenied):
        call(manager, "base.blueprint.import", template="restaurant.es")
    assert not ImportBatch.objects.exists()


def test_an_unknown_template_is_not_found(owner):
    with pytest.raises(NotFound) as refused:
        call(owner, "base.blueprint.import", template="bakery.es")
    assert refused.value.code == "base.template_not_found"


@pytest.mark.parametrize("source", [{}, {"template": "restaurant.es", "file_base64": "UEsF"}])
def test_a_load_names_one_source(owner, source):
    with pytest.raises(InvalidPayload) as refused:
        call(owner, "base.blueprint.import", **source)
    assert refused.value.code == "base.blueprint_source"


def test_only_the_apps_chosen_load(owner):
    loaded = call(owner, "base.blueprint.import", template="restaurant.es", apps=["table"])

    assert total(owner, "inventory.product.list") == 0
    assert total(owner, "table.table.list") == 10
    assert ImportBatch.objects.get(pk=loaded.id).apps == ["table"]


# ── Load a file (BASE-G104) ────────────────────────────────────────────────────────────────────────────────────────


def test_an_uploaded_file_loads_like_a_template(owner):
    loaded = call(owner, "base.blueprint.import", file_base64=a_file())

    assert (loaded.name, loaded.source, loaded.status, loaded.rows) == ("Bar Pepe", "file", "complete", 1)
    assert [row.name for row in call(owner, "table.zone.list", limit=10).rows] == ["Patio"]
    assert ImportBatch.objects.get(pk=loaded.id).template_key == ""


def test_a_file_that_is_not_a_blueprint_is_refused_with_its_reason(owner):
    with pytest.raises(InvalidPayload) as refused:
        call(owner, "base.blueprint.import", file_base64=base64.b64encode(b"hello").decode())

    assert refused.value.code == "base.blueprint_invalid"
    assert refused.value.message == "No es un fichero .blueprint.zip."
    assert not ImportBatch.objects.exists()


# ── Retry what did not go in (BASE-G107) ───────────────────────────────────────────────────────────────────────────


def a_partial_load(owner, monkeypatch):
    """A load whose tables did not go in (the app was off then)."""
    with monkeypatch.context() as patch:
        patch.setattr(blueprint, "active_apps", lambda scope: frozenset({"inventory"}))
        return call(owner, "base.blueprint.import", template="restaurant.es", apps=["inventory", "table"])


def test_retrying_loads_only_what_did_not_go_in(owner, monkeypatch):
    first = a_partial_load(owner, monkeypatch)
    assert first.status == "partial"

    retried = call(owner, "base.blueprint.import", retry_of=first.id)

    batch = ImportBatch.objects.get(pk=retried.id)
    assert (retried.status, batch.retry_of_id, batch.apps) == ("complete", first.id, ["inventory", "table"])
    assert set(batch.created_rows) == {"table.zone", "table.table"}  # the products were there already
    assert total(owner, "inventory.product.list") == 16
    assert total(owner, "table.table.list") == 10


def test_a_load_from_a_file_cannot_be_retried(owner):
    partial = call(
        owner,
        "base.blueprint.import",
        file_base64=a_file(data={"table.table": [{"number": "1", "zone": "Nowhere", "capacity": 4}]}),
    )
    assert partial.status == "failed"

    with pytest.raises(Conflict) as refused:
        call(owner, "base.blueprint.import", retry_of=partial.id)
    assert refused.value.code == "base.import_from_file"


def test_a_load_whose_template_changed_since_is_not_retried(owner, monkeypatch):
    first = a_partial_load(owner, monkeypatch)
    ImportBatch.objects.filter(pk=first.id).update(template_version="0")

    with pytest.raises(Conflict) as refused:
        call(owner, "base.blueprint.import", retry_of=first.id)
    assert refused.value.code == "base.template_version_gone"


def test_a_load_that_went_in_whole_has_nothing_to_retry(owner):
    whole = call(owner, "base.blueprint.import", template="restaurant.es")

    with pytest.raises(Conflict) as refused:
        call(owner, "base.blueprint.import", retry_of=whole.id)
    assert refused.value.code == "base.import_complete"


# ── Undo a load (BASE-G108) ────────────────────────────────────────────────────────────────────────────────────────


def test_undoing_a_load_removes_its_rows_and_marks_it_undone(owner):
    loaded = call(owner, "base.blueprint.import", template="restaurant.es")

    undone = call(owner, "base.import.undo", id=loaded.id)

    assert total(owner, "inventory.product.list") == 0
    assert total(owner, "table.table.list") == 0
    assert {(app.id, app.removed, app.failed) for app in undone.apps} == {("inventory", 22, 0), ("table", 12, 0)}
    assert ImportBatch.objects.get(pk=loaded.id).undone_at is not None
    assert events("base.import.undone") == [{"id": str(loaded.id)}]


def test_a_load_is_undone_once(owner):
    loaded = call(owner, "base.blueprint.import", template="restaurant.es")
    call(owner, "base.import.undo", id=loaded.id)

    with pytest.raises(Conflict) as refused:
        call(owner, "base.import.undo", id=loaded.id)
    assert refused.value.code == "base.import_undone"


def test_undoing_an_unknown_load_is_not_found(owner):
    with pytest.raises(NotFound) as refused:
        call(owner, "base.import.undo", id="01900000-0000-7000-8000-000000000000")
    assert refused.value.code == "base.import_not_found"


def test_who_does_not_run_the_hub_cannot_undo(owner, manager):
    loaded = call(owner, "base.blueprint.import", template="restaurant.es")

    with pytest.raises(PermissionDenied):
        call(manager, "base.import.undo", id=loaded.id)


# ── Reset by sections (BASE-G109) ──────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def own_database(monkeypatch):
    """The hub has its own database (phase 2): its reset touches no one else's data."""
    monkeypatch.setattr(services, "has_own_database", lambda hub: True)


def test_the_plan_says_what_each_app_would_lose_and_what_to_type(owner):
    Hub.objects.filter(slug="a").update(name="Bar Pepe")
    call(owner, "base.blueprint.import", template="restaurant.es")

    plan = call(owner, "base.hub.reset", dry_run=True)

    assert plan.dry_run is True
    assert plan.confirm_with == "Bar Pepe"
    assert {(section.id, section.label, section.rows) for section in plan.sections} == {
        ("inventory", "Inventario", 22),
        ("table", "Mesas", 12),
    }
    assert total(owner, "inventory.product.list") == 16  # nothing removed


def test_without_a_business_name_the_hubs_address_is_typed(owner):
    assert call(owner, "base.hub.reset", dry_run=True).confirm_with == "a"


def test_in_phase_1_the_reset_says_why_it_is_not_available_and_removes_nothing(owner):
    call(owner, "base.blueprint.import", template="restaurant.es")

    plan = call(owner, "base.hub.reset", dry_run=True)
    with pytest.raises(Conflict) as refused:
        call(owner, "base.hub.reset", apps=["table"], confirm="a")

    assert plan.available is False
    assert refused.value.code == "base.reset_shared_database"
    # What the person reads says it is not available yet, never that their data sits with other businesses' (nothing
    # of the infrastructure, nothing that sounds like a leak).
    assert refused.value.message == (
        "Restablecer el negocio todavía no está disponible. Deshaz una importación o quita lo que quieras desde cada app."
    )
    assert total(owner, "table.table.list") == 10


def test_resetting_removes_the_sections_chosen(owner, own_database):
    call(owner, "base.blueprint.import", template="restaurant.es")

    done = call(owner, "base.hub.reset", apps=["table"], confirm="a")

    assert total(owner, "table.table.list") == 0
    assert total(owner, "inventory.product.list") == 16
    assert [(app.id, app.removed) for app in done.apps] == [("table", 12)]
    assert events("base.hub.data_reset") == [{"apps": ["table"]}]


def test_the_name_is_compared_as_the_confirmation_dialog_does(owner, own_database):
    """Spaces around and inside collapsed and case ignored, accents kept (ConfirmDialog of @erplora/ui)."""
    Hub.objects.filter(slug="a").update(name="Bar  Pepé")
    call(owner, "base.blueprint.import", template="restaurant.es")

    call(owner, "base.hub.reset", apps=["table"], confirm="  bar pepé ")

    assert total(owner, "table.table.list") == 0


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"apps": ["table"], "confirm": "b"}, "confirm"),
        ({"apps": ["table"], "confirm": "á"}, "confirm"),  # accents count, as in the confirmation dialog
        ({"apps": [], "confirm": "a"}, "apps"),
        ({"apps": ["bakery_oven"], "confirm": "a"}, "apps"),
    ],
)
def test_a_reset_without_the_exact_name_or_a_section_removes_nothing(owner, own_database, data, field):
    call(owner, "base.blueprint.import", template="restaurant.es")

    with pytest.raises(InvalidPayload) as refused:
        call(owner, "base.hub.reset", **data)

    assert list(refused.value.fields) == [field]
    assert total(owner, "table.table.list") == 10


def test_who_does_not_run_the_hub_cannot_reset(manager, own_database):
    with pytest.raises(PermissionDenied):
        call(manager, "base.hub.reset", dry_run=True)


# ── A business born with every app off (round 2026-10-27): the blueprint turns its apps on, then loads ──────────────

C = Scope("host", "c")


@pytest.fixture
def born():
    """A business as it is born: ready in the registry, every app off (no row), and its owner."""
    Hub.objects.create(slug="c", status=Hub.Status.READY)
    user = get_user_model().objects.create_user(username="carla", password="pw")
    Membership.objects.create(user=user, host="c", role=Membership.Role.OWNER)
    return OperationContext(scope=C, actor=user, permissions=permissions_for(user, C), language="es")


def modules_on(scope=C):
    return set(relay.active_apps(scope)) & set(activation.module_graph())


def chosen(host="c"):
    return set(AppActivation.objects.filter(host=host, state="on", chosen=True).values_list("app", flat=True))


def enabled_events(host="c"):
    return sorted(
        OutboxEvent.objects.filter(name=base_events.APP_ENABLED, scope_key=host).values_list("payload__app", flat=True)
    )


@pytest.fixture
def load(django_capture_on_commit_callbacks):
    """``base.blueprint.import`` as a request runs it: what runs after its COMMIT (the cache of the apps off forgotten)
    runs too, so what the test reads next sees the apps it turned on."""

    def run(ctx, **data):
        with django_capture_on_commit_callbacks(execute=True):
            return call(ctx, "base.blueprint.import", **data)

    return run


def with_max_apps(slug, max_apps):
    Hub.objects.filter(slug=slug).update(
        state={"plan": {"slug": "free", "max_users": 0, "max_devices": 0, "max_apps": max_apps}}, state_version=1
    )


def test_a_template_turns_on_its_apps_and_then_loads_them(born, load):
    assert modules_on() == set()
    apps = template_apps("restaurant")
    roots = activation.roots(apps, activation.module_graph())

    loaded = load(born, template="restaurant.es")

    assert modules_on() == set(apps)
    # Only its roots are chosen (what the plan's limit counts); what they need came along, as base.app.enable does.
    assert chosen() == roots and len(roots) == 13
    assert enabled_events() == sorted(roots)
    assert (loaded.status, loaded.rows) == ("complete", 34)
    assert total(born, "inventory.product.list") == 16
    assert total(born, "table.table.list") == 10
    assert all(app.reason == "" for app in loaded.report.apps)


def test_only_the_apps_chosen_are_turned_on(born, load):
    loaded = load(born, template="restaurant.es", apps=["table"])

    assert modules_on() == {"table"} | activation.needs(["table"], activation.module_graph())
    assert chosen() == {"table"}
    assert "inventory" not in modules_on()
    assert total(born, "table.table.list") == 10
    assert {app.id: app.status for app in loaded.report.apps}["inventory"] == "not_selected"


def test_an_app_beyond_the_plans_limit_stays_off_says_why_and_the_rest_loads(born, load):
    with_max_apps("c", 1)
    file = a_file(
        apps=("inventory", "table"),
        data={
            "inventory.category": [{"name": "Bebidas", "description": ""}],
            "table.zone": [{"name": "Patio", "description": "", "color": "warning", "sort_order": 1}],
        },
    )

    loaded = load(born, file_base64=file)

    assert chosen() == {"inventory"}
    assert "table" not in modules_on()
    with pytest.raises(services.AppLimitReached) as refused:
        call(born, "base.app.enable", app="table")
    report = {app.id: app for app in loaded.report.apps}
    assert (report["inventory"].status, report["inventory"].reason) == ("applied", "")
    assert (report["table"].status, report["table"].reason) == ("inactive", refused.value.message)
    assert report["table"].reason.strip()
    assert loaded.status == "partial"
    assert [row.name for row in call(born, "inventory.category.list", limit=10).rows] == ["Bebidas"]


def test_a_paid_app_without_its_right_stays_off_and_says_why(born, load, monkeypatch):
    from django.apps import apps as django_apps

    from base import entitlement

    monkeypatch.setattr(django_apps.get_app_config("table"), "premium", True)

    loaded = load(born, template="restaurant.es")

    table = next(app for app in loaded.report.apps if app.id == "table")
    assert (table.status, table.reason) == ("inactive", entitlement.refused("table", "es").message)
    assert "table" not in modules_on()
    assert total(born, "inventory.product.list") == 16


def test_a_backup_turns_on_its_apps_too(born, load):
    backup = a_file(
        purpose="backup",
        apps=("customer",),
        data={"customer.customer": [{"name": "Lucía Pérez", "email": "lucia@example.com", "phone": ""}]},
    )

    loaded = load(born, file_base64=backup)

    assert modules_on() == {"customer"}
    assert chosen() == {"customer"}
    assert loaded.status == "complete"
    assert total(born, "customer.customer.list") == 1


def test_the_apps_just_turned_on_load_though_the_cache_still_had_them_off(born, load):
    """The apps off are cached per business (``base.activation``); the load reads what it turned on, never the cache."""
    assert "inventory" in activation.off_apps(C)  # kept in the cache now

    load(born, template="restaurant.es")

    assert total(born, "inventory.product.list") == 16


def test_an_app_already_on_is_left_as_it_is(owner, load):
    """``a`` has every app on: the load turns nothing on and records no change."""
    load(owner, template="restaurant.es")

    assert enabled_events("a") == []
    assert total(owner, "inventory.product.list") == 16


def test_a_business_outside_spain_gets_verifactu_from_a_template_as_apps_would_give_it(born, load):
    """VeriFactu files only for Spain (VERIFACTU-F01, hub#274): outside it, turning it on is allowed and it stays
    inert, so nothing refuses it. The template turns it on through the same ``base.app.enable`` as Apps: on, with no
    reason against it, and the rest of the template loads."""
    Hub.objects.filter(slug="c").update(country="PL")

    loaded = load(born, template="restaurant.es")

    verifactu = next(app for app in loaded.report.apps if app.id == "verifactu")
    assert verifactu.reason == ""
    assert "verifactu" in modules_on()
    assert loaded.status == "complete"

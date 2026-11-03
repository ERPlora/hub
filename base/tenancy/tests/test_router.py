"""``TenantRouter`` (PLAN-DB §4; plan 2026-10-22-fase-2-tenencia §2.2, §2.7 and §4, step 5).

Control's models always go to ``default``; a hub's go to the alias of the active ``use_hub`` and, without one, fail
(``HubContextMissing``): they never fall back to ``default``. The outbox follows the context (control's for the
registry). Relations stay inside one database, compared by database, not by alias. Control's apps migrate only on
``default``; a hub's only on a migrator's ``…__ddl`` alias, never on ``default`` (S5: phase 1's shared database is
gone). ``migrate`` on a hub's alias is refused.
"""

import uuid
from types import SimpleNamespace

import pytest
from django.db import connections as django_connections
from live.models import OutboxEvent

from apps.demo.models import Item
from base.models import Membership, TaskSchedule
from base.tenancy import connections, context, names
from base.tenancy.context import HubContextMissing
from base.tenancy.inventory import UnclassifiedModel
from base.tenancy.router import TenantRouter
from base.models import Hub

router = TenantRouter()

pytestmark = pytest.mark.usefixtures("no_test_fallback")


@pytest.fixture(autouse=True)
def restored_settings(monkeypatch):
    monkeypatch.setattr(django_connections, "settings", django_connections.settings)


@pytest.fixture
def hub_alias():
    """A hub's alias registered as ``use_hub`` would, without touching its (absent) database."""
    hub_id = uuid.uuid7()
    hub = SimpleNamespace(id=hub_id, slug="acme", db_name=names.hub_db_name(connections.control_name(), hub_id))
    return connections.register_hub_alias(hub), hub


def in_hub(alias, hub):
    return context._entered(context.DatabaseContext(kind=context.HUB, alias=alias, hub=hub))


@pytest.mark.parametrize("model", [Hub, Membership])
def test_controls_models_go_to_default_with_or_without_a_context(model, hub_alias):
    assert router.db_for_read(model) == "default"
    assert router.db_for_write(model) == "default"
    with in_hub(*hub_alias):
        assert router.db_for_write(model) == "default"


@pytest.mark.parametrize("model", [Item, TaskSchedule])
def test_a_hubs_model_goes_to_the_alias_of_its_hub(model, hub_alias):
    alias, hub = hub_alias
    with in_hub(alias, hub):
        assert router.db_for_read(model) == alias
        assert router.db_for_write(model) == alias


@pytest.mark.parametrize("model", [Item, TaskSchedule, OutboxEvent])
def test_a_hubs_model_without_a_context_never_reaches_default(model):
    with pytest.raises(HubContextMissing):
        router.db_for_read(model)
    with pytest.raises(HubContextMissing):
        router.db_for_write(model)


def test_a_hubs_model_on_control_is_refused_and_the_outbox_goes_to_control():
    with context.use_control():
        with pytest.raises(HubContextMissing):
            router.db_for_write(Item)
        assert router.db_for_write(OutboxEvent) == "default"


def test_the_outbox_follows_the_hub(hub_alias):
    alias, hub = hub_alias
    with in_hub(alias, hub):
        assert router.db_for_write(OutboxEvent) == alias


def test_a_model_nobody_classified_is_refused():
    stranger = SimpleNamespace(
        _meta=SimpleNamespace(label_lower="audit.entry", app_label="audit", app_config=SimpleNamespace(name="audit"))
    )
    with context.use_control(), pytest.raises(UnclassifiedModel):
        router.db_for_read(stranger)


def _on(alias: str):
    return SimpleNamespace(_state=SimpleNamespace(db=alias))


def test_relations_stay_inside_one_database_whatever_the_alias(hub_alias):
    alias, hub = hub_alias
    ddl = connections.register_ddl_alias(hub.db_name)

    assert router.allow_relation(_on(alias), _on(ddl)) is True
    assert router.allow_relation(_on(alias), _on(alias)) is True
    assert router.allow_relation(_on(alias), _on("default")) is False
    assert router.allow_relation(_on("default"), _on("default")) is True
    assert router.allow_relation(_on(None), _on(alias)) is None


@pytest.mark.parametrize(
    ("app_label", "model_name", "on_default", "on_ddl", "on_hub_alias", "on_template"),
    [
        ("control", "hub", True, False, False, False),
        ("auth", "user", True, False, False, False),
        ("contenttypes", None, True, False, False, False),
        ("base", "membership", True, False, False, False),
        ("base", "hub", True, False, False, False),  # the registry before it moved
        ("base", "taskschedule", False, True, False, False),
        ("base", None, False, True, False, False),
        ("demo", "item", False, True, False, False),
        ("demo", None, False, True, False, False),
        ("live", "outboxevent", True, True, False, False),
        ("base", "eventdelivery", True, True, False, False),
    ],
)
def test_who_migrates_where(hub_alias, app_label, model_name, on_default, on_ddl, on_hub_alias, on_template):
    alias, hub = hub_alias
    ddl = connections.register_ddl_alias(hub.db_name)

    assert router.allow_migrate("default", app_label, model_name=model_name) is on_default
    assert router.allow_migrate(ddl, app_label, model_name=model_name) is on_ddl
    assert router.allow_migrate(alias, app_label, model_name=model_name) is on_hub_alias
    assert router.allow_migrate(connections.TEMPLATE_ALIAS, app_label, model_name=model_name) is on_template


def test_the_shared_app_is_left_to_the_shared_router():
    assert router.allow_migrate("default", "shared", model_name="app") is None
    assert router.db_for_read(SimpleNamespace(_meta=SimpleNamespace(
        label_lower="shared.app", app_label="shared", app_config=SimpleNamespace(name="shared")
    ))) is None


def test_an_object_related_to_a_loaded_one_lives_in_its_database(hub_alias):
    alias, _hub = hub_alias
    loaded = Item()
    loaded._state.db = alias

    assert router.db_for_write(Item, instance=loaded) == alias
    with context.use_control():
        assert router.db_for_write(Hub, instance=loaded) == "default"


def test_a_control_objects_hint_never_sends_a_hubs_model_to_default(hub_alias):
    """A reverse relation from a control object (``user.<hub model>_set`` through the AUTH_USER_MODEL links of staff,
    attendance, task, whatsapp_inbox) hints ``default``: the hub's model still goes to the hub of the context."""
    from django.contrib.auth import get_user_model

    alias, hub = hub_alias
    user = get_user_model()()
    user._state.db = "default"

    with in_hub(alias, hub):
        assert router.db_for_read(Item, instance=user) == alias
        assert router.db_for_write(Item, instance=user) == alias
    with pytest.raises(HubContextMissing):
        router.db_for_read(Item, instance=user)

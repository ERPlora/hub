"""No hub shares control's database: the local hubs a and b get their own once every app can live in one
(``seed_local_hubs``), and every hub the services make names its own."""

import ast
from pathlib import Path

import pytest
from psycopg import sql
from django.utils import timezone
from live.models import OutboxEvent

from base.tenancy import connections as tenancy_connections, migrator, names
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from base.tenancy.tests.test_provision import databases, fresh, nothing_checked_yet
from control.models import Hub

#: The provisioning tests' own autouse fixture.
__all__ = ["nothing_checked_yet"]

HUB_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture
def every_app_portable():
    """Every app a and b turn on can live in a hub's own database."""
    assert migrator.hub_apps() == frozenset(migrator.portable_apps())


@pytest.fixture
def plain_template(django_db_blocker, hub_databases):
    """``<control>_template`` (a hub with no vertical, as a and b), a copy of the tests' own."""
    control = hub_databases.control
    name = names.template_db_name(control)
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                names.identifier(name, control=control), names.identifier(hub_databases.template, control=control)
            )
        )
    yield name
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)


def test_seed_local_hubs_gives_a_and_b_their_own_databases_once_every_app_can_live_in_one(
    django_db_blocker, settings, every_app_portable, plain_template, told
):
    from io import StringIO

    from django.core.management import call_command

    from base.models.activation import AppActivation

    settings.DEBUG = True
    started = timezone.now()
    out = StringIO()
    with django_db_blocker.unblock():
        try:
            call_command("seed_local_hubs", stdout=out)
            local = {hub.slug: hub for hub in Hub.objects.filter(slug__in=["a", "b"])}
            assert sorted(local) == ["a", "b"]
            for hub in local.values():
                assert (hub.status, hub.db_name) == ("ready", names.hub_db_name(tenancy_connections.control_name(), hub.id))
                assert hub.db_name in databases()
                with use_hub(hub):
                    turned_on = set(AppActivation.objects.filter(host=hub.slug, state="on").values_list("app", flat=True))
                assert {label for label in migrator.portable_apps() if label not in ("base", "live")} <= turned_on
            assert "a: created (its own database)" in out.getvalue()
            # A second run leaves them as they are; one left cancelled is ready again, on the database it has.
            with use_hub(local["b"]):
                AppActivation.objects.filter(host="b", app="task").update(state="off")
            with use_hub(local["a"]):
                a_on = set(AppActivation.objects.filter(host="a", state="on").values_list("app", flat=True))
                AppActivation.objects.filter(host="a").delete()
            again = StringIO()
            call_command("seed_local_hubs", stdout=again)
            assert "a: already ready" in again.getvalue()
            # As one that shares control's: a local hub left with no app at all has every app on again; one that
            # turned some off keeps them off.
            with use_hub(local["a"]):
                assert set(AppActivation.objects.filter(host="a", state="on").values_list("app", flat=True)) == a_on
            with use_hub(local["b"]):
                assert AppActivation.objects.get(host="b", app="task").state == "off"
            Hub.objects.filter(slug="a").update(status=Hub.Status.CANCELLED)
            back = StringIO()
            call_command("seed_local_hubs", stdout=back)
            assert "a: ready again" in back.getvalue()
            assert (fresh(local["a"]).status, fresh(local["a"]).db_name) == ("ready", local["a"].db_name)
        finally:
            leftover = list(Hub.objects.filter(slug__in=["a", "b"]))
            with hubs._maintenance() as conn:
                for hub in leftover:
                    if hub.db_name:
                        hubs._drop(conn, hub.db_name, tenancy_connections.control_name())
            Hub.objects.filter(slug__in=["a", "b"]).delete()
            with use_control():
                OutboxEvent.objects.filter(created_at__gte=started).delete()
    assert told == []  # the local hubs are no business of the SaaS's


# ── Guardrail: no new hub is ever born sharing control's database ───────────────────────────────────────────────────

#: The ``Hub.objects.create`` calls of ``base/services/`` that may leave ``db_name`` empty, each with its reason.
#: None: the old shared database is gone, every hub is born with its own (the local ones included).
SHARED_HUB_CREATES: dict[str, str] = {}


#: The manager's methods that make a row.
MAKERS = ("create", "get_or_create", "update_or_create")


def _on_hub_objects(node: ast.AST) -> bool:
    """Whether the chain ``node`` hangs from is ``Hub.objects…`` (``Hub.objects.select_for_update().create`` too)."""
    while isinstance(node, (ast.Attribute, ast.Call)):
        if isinstance(node, ast.Call):
            node = node.func
            continue
        if node.attr == "objects" and isinstance(node.value, ast.Name) and node.value.id == "Hub":
            return True
        node = node.value
    return False


def hub_creates(source: str) -> list[tuple[str, bool]]:
    """``(function, names db_name)`` for every row ``Hub.objects…create(…)`` makes in ``source``."""
    found = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in MAKERS
                and _on_hub_objects(node.func.value)
            ):
                keywords = {keyword.arg for keyword in node.keywords}
                defaults = next((kw.value for kw in node.keywords if kw.arg in ("defaults", "create_defaults")), None)
                if isinstance(defaults, ast.Dict):
                    keywords |= {key.value for key in defaults.keys if isinstance(key, ast.Constant)}
                found.append((function.name, "db_name" in keywords))
    return found


def test_the_scanner_sees_a_hub_made_with_and_without_its_database():
    source = (
        "def good(data):\n    Hub.objects.create(id=data.id, db_name=name)\n"
        "def bad(data):\n    Hub.objects.create(id=data.id)\n"
        "def seeded(slug):\n    Hub.objects.get_or_create(slug=slug, defaults={'db_name': name})\n"
        "def locked(slug):\n    Hub.objects.select_for_update().get_or_create(slug=slug)\n"
        "def other(slug):\n    Membership.objects.create(host=slug)\n"
    )

    assert hub_creates(source) == [("good", True), ("bad", False), ("seeded", True), ("locked", False)]


def test_every_hub_the_services_make_names_its_own_database_but_the_listed_ones():
    found = [one for module in (HUB_DIR / "base" / "services").glob("*.py") for one in hub_creates(module.read_text())]

    assert {"_requested", "demo_create", "hub_seed_local"} <= {function for function, _named in found}
    offenders = sorted({function for function, named in found if not named} - set(SHARED_HUB_CREATES))
    assert offenders == [], (
        "A new hub is born with its own database: name its db_name "
        f"(base.tenancy.names) or list the call in SHARED_HUB_CREATES with its reason: {offenders}"
    )

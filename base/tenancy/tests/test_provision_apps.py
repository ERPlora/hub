"""The apps and the tables a hub is born with: its template's, those of the apps its country requires that the
platform turns on (Taxes, never VeriFactu), and those it is asked for, each in its own database."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from django.apps import apps as django_apps

from live.context import OperationContext, Scope
from live.operations import get as get_operation

from base import activation, services
from base.activation import Activation
from base.models.activation import AppActivation
from base.schemas.home import SetupStatusIn
from base.tenancy import connections as tenancy_connections, migrator, names, provision
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tenancy.tests.test_provision import control_hears, fresh, nothing_checked_yet
from control.models import Hub, HubDue

#: The provisioning tests' own autouse fixture.
__all__ = ["nothing_checked_yet"]


# ── More apps than the template's ───────────────────────────────────────────────────────────────────────────────────


def built_template(django_db_blocker, hub_databases, vertical: str, apps) -> Iterator[str]:
    """``<control>_template_<vertical>`` with the tables of ``apps``, made before its test and dropped after it."""
    control = hub_databases.control
    name = names.template_db_name(control, vertical)
    with django_db_blocker.unblock():
        with hubs._maintenance() as conn:
            hubs._drop(conn, name, control)
            conn.execute(sql.SQL("CREATE DATABASE {}").format(names.identifier(name, control=control)))
        ddl = tenancy_connections.register_ddl_alias(name)
        try:
            migrator.migrate_apps(ddl, apps)
        finally:
            migrator._forget_alias(ddl)  # closed and out of the settings: Django's test case unwraps only its own
    yield name
    with hubs._maintenance() as conn:
        hubs._drop(conn, name, control)


@pytest.fixture
def small_template(django_db_blocker, hub_databases):
    """``<control>_template_small``: ``base`` alone (and what it needs), built as the tests' template is."""
    yield from built_template(django_db_blocker, hub_databases, "small", ["base"])


def test_a_hub_may_get_more_apps_than_its_template_and_a_seed_inside_its_database(registry, small_template, told):
    hub = registry.hub(vertical="small")
    seeded = []

    def seed(row):
        from base.tenancy.context import current

        seeded.append(current().alias)

    assert not {table for table in hubs.table_names(small_template) if table.startswith("tax_")}
    assert provision.provision(hub, apps=["tax"], seed=seed) is True

    hub = fresh(hub)
    assert {table for table in hubs.table_names(hub.db_name) if table.startswith("tax_")}
    assert "tax" in hub.schema_apps and "base" in hub.schema_apps
    assert seeded == [tenancy_connections.hub_alias(hub)]


def _only_its_templates_apps_are_there(hub: Hub) -> None:
    """A new hub has its template's tables and those of the apps it is born with on (Taxes), nothing more,
    every other app off; an app's tables are made the first time it is turned on (``base.app.enable`` → the worker's
    ``ensure_schema``)."""
    hub = fresh(hub)
    assert hub.status == "ready"
    assert set(hub.schema_apps) == {"base", "live", "tax"}
    tables = hubs.table_names(hub.db_name)
    assert {table for table in tables if table.startswith("tax_")}
    assert not {table for table in tables if table.startswith(("sale_", "customer_"))}
    with use_hub(hub):
        assert set(AppActivation.objects.filter(state="on").values_list("app", flat=True)) == {"tax"}


def test_a_new_hub_gets_only_its_templates_tables_and_those_of_what_it_is_born_with(registry, small_template, told):
    hub = registry.hub(vertical="small")
    assert not {table for table in hubs.table_names(small_template) if table.startswith("sale_")}

    assert provision.provision(hub) is True

    _only_its_templates_apps_are_there(hub)


def test_the_due_pass_gives_a_new_business_only_its_templates_tables(registry, small_template, told):
    hub = registry.hub(vertical="small")
    HubDue.mark_due(hub)

    provision.run_due()

    _only_its_templates_apps_are_there(hub)


# ── What a business is born with ────────────────────────────────────────────────────────────────────────────────────
# Its seeding turns on, by itself, the apps the business's country requires that say the platform may (Taxes, in every
# country), none chosen: they take nothing of the plan's limit. Never VeriFactu, mandatory in Spain: it binds the
# business to the AEAT, so the Home asks its owner to turn it on. Every other app is off.


def admin(hub: Hub, language: str = "en") -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=frozenset({"*"}), language=language)


def born_with(hub: Hub) -> tuple[dict[str, Activation], dict[str, dict]]:
    """The apps of ``hub`` once born, and what «Finish setting up your business» asks its owner, read in its database."""
    with use_hub(fresh(hub)):
        states = activation.states_of(Scope("host", hub.slug))
        document = get_operation("base.setup.status")(admin(hub), SetupStatusIn()).model_dump(mode="json")
    return states, {item["key"]: item for item in document["items"]}


@pytest.mark.parametrize(
    ("country", "verifactu_asked", "rules"),
    [("ES", True, "done"), ("", True, "done"), ("PT", False, "pending")],
)
def test_a_business_is_born_with_taxes_on_for_its_country_and_never_with_verifactu(
    registry, told, country, verifactu_asked, rules
):
    """Taxes is on and not chosen from its sign-up, with its country's rules: Spain's (a business without a country, a
    demo, is in Spain) price at once, one of Portugal is told it has none yet (TAX-F17). VeriFactu stays off: in Spain
    the Home asks its owner to turn it on; elsewhere, nothing."""
    hub = registry.hub(country=country)

    assert provision.provision(hub) is True

    states, asked = born_with(hub)
    assert states["tax"] == Activation("on", False)
    assert states["verifactu"] == Activation("off", False)
    assert {label for label, row in states.items() if row.wanted} == {"tax"}
    assert activation.chosen_on(states) == 0
    assert "base.mandatory.tax" not in asked
    # With only what it is born with on, its till has nothing to sell yet: «Your apps» still asks for one.
    assert asked["base.apps"]["state"] == "pending"
    assert asked["tax.rules"]["state"] == rules
    assert ("base.mandatory.verifactu" in asked) is verifactu_asked
    if verifactu_asked:
        assert asked["base.mandatory.verifactu"]["state"] == "pending"


def test_two_businesses_are_born_each_with_its_apps_in_its_own_database_and_none_in_control(registry, told):
    """A business of Spain and one of Portugal, each with its rows in its own database; the second sign-up leaves the
    first's as they were, and control hears none of their apps."""
    spain, portugal = registry.hub(country="ES"), registry.hub(country="PT")

    with control_hears() as heard:
        assert provision.provision(spain) is True
        with use_hub(fresh(spain)):
            first = set(AppActivation.objects.values_list("host", "app", "state", "chosen", "changed_at"))
        assert provision.provision(portugal) is True

    assert not [sql for sql in heard if "base_appactivation" in sql]
    with use_hub(fresh(spain)):
        assert set(AppActivation.objects.values_list("host", "app", "state", "chosen", "changed_at")) == first
    with use_hub(fresh(portugal)):
        assert set(AppActivation.objects.values_list("host", flat=True)) == {portugal.slug}
        assert set(AppActivation.objects.filter(state="on").values_list("app", flat=True)) == {"tax"}
    assert {host for host, *_ in first} == {spain.slug}


def test_a_demo_is_born_as_a_business_of_spain_with_taxes_on_and_verifactu_off(registry, told):
    hub = registry.hub(demo=True)

    assert provision.provision(hub) is True

    states, asked = born_with(hub)
    assert {label for label, row in states.items() if row.wanted} == {"tax"}
    assert asked["base.mandatory.verifactu"]["state"] == "pending"


def test_an_app_mandatory_in_one_country_that_the_platform_turns_on_is_on_only_in_a_business_of_it(
    registry, small_template, told, monkeypatch
):
    """Base names no app: what it turns on at sign-up, with its tables, is what each app declares, for the business's own
    country (a straw declaration on Tasks, mandatory in Portugal only; a template without its tables)."""
    monkeypatch.setattr(
        django_apps.get_app_config("task"), "mandatory", {"countries": ["PT"], "platform_turns_on": True}, raising=False
    )
    portugal, spain = registry.hub(country="PT", vertical="small"), registry.hub(country="ES", vertical="small")

    assert provision.provision(portugal) is True
    assert provision.provision(spain) is True

    assert born_with(portugal)[0]["task"] == Activation("on", False)
    assert born_with(spain)[0]["task"] == Activation("off", False)
    assert "task" in fresh(portugal).schema_apps and "task" not in fresh(spain).schema_apps


def test_what_its_seeding_read_of_its_apps_is_not_kept_once_it_is_born_with_them(registry, told):
    """Read while it is seeded (its apps all off then), what is kept of them is forgotten once it is born with Taxes on:
    Taxes answers from its first request, never refused for a minute as off."""
    hub = registry.hub(country="ES")
    read: list[frozenset[str]] = []

    def seed(row):
        read.append(activation.off_apps(Scope("host", row.slug)))

    assert provision.provision(hub, seed=seed) is True

    assert "tax" in read[0]
    with use_hub(fresh(hub)):
        assert "tax" not in activation.off_apps(Scope("host", hub.slug))


def test_a_seeding_that_writes_its_apps_keeps_them_as_it_wrote_them(registry, told):
    """The local hubs a and b are born with every app on (``seed_local_hubs``): their seeding writes their apps, and
    what a business is born with adds nothing to them."""
    hub = registry.hub()

    assert provision.provision(hub, seed=services.hub_registry.turn_every_app_on) is True

    states, _ = born_with(hub)
    assert states == activation.every_on(activation.module_graph())


@pytest.fixture
def full_template(django_db_blocker, hub_databases):
    """``<control>_template_full``: built as ``migrate_hubs`` builds the platform's (``migrator.templates()[0].apps``)."""
    yield from built_template(django_db_blocker, hub_databases, "full", migrator.templates()[0].apps)


def test_a_sign_up_from_a_template_up_to_date_is_the_clone_alone(registry, full_template, monkeypatch, told):
    """The templates carry every portable app (``migrator.templates``), so a hub made from one migrates nothing: its
    sign-up is the clone, never a minute of migrations on Fargate."""
    hub = registry.hub(vertical="full")
    applied = []
    real = migrator.ensure_schema
    monkeypatch.setattr(migrator, "ensure_schema", lambda row, **kwargs: applied.append(real(row, **kwargs)) or applied[-1])

    assert provision.provision(hub) is True

    assert applied == [[]]
    assert set(migrator.portable_apps()) <= set(fresh(hub).schema_apps)

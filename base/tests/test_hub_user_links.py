"""Every app fits a hub's own database: the people of the business are its own.

A staff record, its time off, a clock-in, a task, its comments and the WhatsApp inbox's assignments and messages hang
from ``base.HubUser``, never from control's ``auth.User``: a key between two databases does not exist
(``tests/test_guardrails.py``, «(h)»). So every app fits, every vertical's template holds its whole list, and the
expand migrations that moved those links, run on a business's own database, find no control users to fill them from
and no key to control's users to drop.
"""

import datetime as dt
import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.db.migrations.loader import MigrationLoader

from base import catalog
from base.models import HubUser
from base.tenancy import inventory, migrator, names
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_auth_views import ON_HUB_A

#: The apps whose links to control's users moved to ``base.HubUser``, and those that waited for them.
PEOPLE_APPS = {"staff", "attendance", "task", "whatsapp_inbox"}
WAITED_FOR_THEM = {"appointment", "online_booking", "service"}
AT = dt.datetime(2026, 10, 6, 7, tzinfo=dt.UTC)

#: Each expand migration: ``(app, migration, the migration it follows, [(model, old field, new field, old column)])``.
EXPANDS = [
    (
        "staff",
        "0004_hub_users",
        "0003_hourly_rate_verbose_name",
        [("member", "user", "hub_user", "user_id"), ("timeoff", "approved_by", "approved_by_hub_user", "approved_by_id")],
    ),
    (
        "attendance",
        "0003_hub_users",
        "0002_correction_author",
        [
            ("record", "created_by", "created_by_hub_user", "created_by_id"),
            ("record", "updated_by", "updated_by_hub_user", "updated_by_id"),
            ("correction", "created_by", "created_by_hub_user", "created_by_id"),
            ("attendancesettings", "updated_by", "updated_by_hub_user", "updated_by_id"),
        ],
    ),
    (
        "task",
        "0002_hub_users",
        "0001_initial",
        [("task", "created_by", "created_by_hub_user", "created_by_id"), ("comment", "author", "author_hub_user", "author_id")],
    ),
    (
        "whatsapp_inbox",
        "0010_hub_users",
        "0009_conversation_needs_attention",
        [
            ("conversation", "assigned_to", "assigned_to_hub_user", "assigned_to_id"),
            ("message", "sent_by", "sent_by_hub_user", "sent_by_id"),
            ("note", "author", "author_hub_user", "author_id"),
        ],
    ),
]


def test_every_hub_app_fits_a_hub_s_own_database():
    every_hub_app = {
        config.label
        for config in apps.get_app_configs()
        if config.name.startswith(inventory.HUB_MODULES_PACKAGE) or inventory.APP_CLASSES.get(config.label) == inventory.HUB
    }

    assert PEOPLE_APPS | WAITED_FOR_THEM <= every_hub_app
    assert set(migrator.portable_apps()) == every_hub_app


@pytest.mark.parametrize(
    ("vertical", "its_people_apps"),
    [
        ("hair_salon", {"staff", "attendance", "task", "whatsapp_inbox", "service", "appointment", "online_booking"}),
        ("restaurant", {"staff", "attendance", "task", "whatsapp_inbox"}),
    ],
)
def test_each_vertical_s_template_holds_its_whole_list(vertical, its_people_apps):
    """The templates ``migrate_hubs`` builds (``migrator.templates``): ``hub_template_<vertical>`` with every app of
    the vertical, none left out."""
    wanted = set(catalog.template_apps(vertical))
    [template] = [
        template for template in migrator.templates("hub") if template.db_name == names.template_db_name("hub", vertical)
    ]

    assert its_people_apps <= wanted
    assert wanted <= set(template.apps)
    assert template.left_out == ()


def test_every_vertical_s_list_fits():
    portable = set(migrator.portable_apps())

    assert {vertical: set(catalog.template_apps(vertical)) - portable for vertical in catalog.known_verticals()} == {
        vertical: set() for vertical in catalog.known_verticals()
    }


def test_the_tests_template_and_its_hubs_have_the_people_apps_tables(hub_databases):
    tables = {"base_hubuser", "staff_member", "staff_timeoff", "service_service", "appointment_appointment"}

    assert PEOPLE_APPS | WAITED_FOR_THEM <= set(hub_databases.apps)
    for database in (hub_databases.template, hub_databases.a, hub_databases.b):
        assert tables <= hubs.table_names(database), database


def _before_the_new_links_take_their_names(app: str, migration: str, previous: str):
    """The apps' state of ``migration``'s ``RunPython`` (its ``AddField`` applied): old and new links side by side."""
    loader = MigrationLoader(connection)
    state = loader.project_state([(app, previous), ("base", "0020_hub_user")])
    for operation in loader.get_migration(app, migration).operations:
        if operation.__class__.__name__ == "RunPython":
            break
        operation.state_forwards(app, state)
    return state.apps


def _row(historical, app: str, model: str, old: str, user):
    """A row of ``app.model`` whose old link ``old`` names control's ``user``, with what the table needs."""

    def staff_member():
        return historical.get_model("staff", "Member").objects.create(first_name="Ana", last_name="López")

    def conversation():
        # One live conversation per number: each row its own.
        phone = f"+346002{historical.get_model('whatsapp_inbox', 'Conversation').objects.count():05d}"
        return historical.get_model("whatsapp_inbox", "Conversation").objects.create(phone=phone)

    def working_day():
        return historical.get_model("attendance", "Record").objects.create(
            member=staff_member(), clock_in_at=AT, work_date=AT.date()
        )

    needs = {
        ("staff", "member"): lambda: {"first_name": "Ana", "last_name": "López"},
        ("staff", "timeoff"): lambda: {
            "member": staff_member(), "start_date": dt.date(2026, 10, 1), "end_date": dt.date(2026, 10, 1)
        },
        ("attendance", "record"): lambda: {"member": staff_member(), "clock_in_at": AT, "work_date": AT.date()},
        ("attendance", "correction"): lambda: {
            "record": working_day(),
            "old_clock_in_at": AT,
            "old_status": "open",
            "new_clock_in_at": AT,
            "new_status": "open",
            "reason": "Forgot to clock out",
        },
        ("attendance", "attendancesettings"): dict,
        ("task", "task"): lambda: {"number": "TSK-20261006-0001", "title": "Restock"},
        ("whatsapp_inbox", "conversation"): lambda: {"phone": "+34600111111"},
        ("whatsapp_inbox", "message"): lambda: {"conversation": conversation(), "direction": "outbound", "kind": "text", "sent_at": AT},
        ("whatsapp_inbox", "note"): lambda: {"conversation": conversation(), "text": "Call back", "created_at": AT},
        ("task", "comment"): lambda: {
            "task": historical.get_model("task", "Task").objects.create(number="TSK-20261006-0002", title="Mop"),
            "text": "On it",
        },
    }
    return historical.get_model(app, model).objects.create(**needs[(app, model)](), **{f"{old}_id": user.pk})


def _migration(app: str, name: str):
    return importlib.import_module(f"apps.{app}.migrations.{name}")


def _keys(database, table: str) -> dict[str, str]:
    """The foreign keys of ``table`` in ``database``: each one's name and the table it points to."""
    with database.cursor() as cursor:
        constraints = database.introspection.get_constraints(cursor, table)
    return {key: details["foreign_key"][0] for key, details in constraints.items() if details["foreign_key"]}


@pytest.mark.parametrize(("app", "name", "previous", "links"), EXPANDS, ids=[expand[0] for expand in EXPANDS])
class TestTheExpand:
    """Each expand migration runs on a business's own database, which holds no control users: nothing to fill from
    them and no key to them to drop. Here it runs on the hub's own alias, inside the test's transaction, which sees the
    test's rows and takes back whatever it would change; the migrator's alias reaches the same database."""

    pytestmark = ON_HUB_A

    def test_a_hub_s_own_database_has_nothing_to_fill(self, app, name, previous, links, hub_a):
        historical = _before_the_new_links_take_their_names(app, name, previous)
        ana = get_user_model().objects.create_user(username="saas:x")
        with use_hub(hub_a):
            rows = {(model, old): _row(historical, app, model, old, ana) for model, old, _new, _column in links}

        _migration(app, name).link_hub_users(historical, SimpleNamespace(connection=connections[hubs.HUB_A_ALIAS]))

        with use_hub(hub_a):
            assert not HubUser.objects.exists()
            for model, old, new, _column in links:
                row = historical.get_model(app, model).objects.get(pk=rows[(model, old)].pk)
                assert getattr(row, f"{new}_id") is None, (model, old)

    def test_a_hub_s_own_database_keeps_its_own_keys(self, app, name, previous, links, hub_a):
        historical = _before_the_new_links_take_their_names(app, name, previous)
        database = connections[hubs.HUB_A_ALIAS]
        tables = {historical.get_model(app, model)._meta.db_table for model, _old, _new, _column in links}
        before = {table: _keys(database, table) for table in tables}

        with database.schema_editor() as editor:
            _migration(app, name).drop_keys_to_control_users(historical, editor)

        assert {table: _keys(database, table) for table in tables} == before
        assert all("base_hubuser" in keys.values() for keys in before.values()), before

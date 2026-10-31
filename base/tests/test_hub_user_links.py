"""Every app fits a hub's own database: the people of the business are its own (tenancy W10; PLAN-DB §2).

Phase 1 hung a staff record, its time off, a clock-in, a task, its comments and the WhatsApp inbox's assignments and
messages from control's ``auth.User``. A key between two databases does not exist, so those apps could not live in a
hub's own database and the templates of the verticals left them out: a hair salon would have been born with no staff,
no services and no appointments. They hang from ``base.HubUser`` now (``tests/test_guardrails.py``, «(h)»), so every
app fits, every vertical's template holds its whole list, and the expand migrations that moved them fill the new links
in phase 1's shared database and nothing in a hub's own.
"""

import datetime as dt
import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from base import catalog
from base.models import HubUser
from base.tenancy import inventory, migrator, names
from base.tenancy.tests import hubs

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


@pytest.mark.django_db
@pytest.mark.parametrize(("app", "name", "previous", "links"), EXPANDS, ids=[expand[0] for expand in EXPANDS])
class TestTheExpand:
    def _rows(self, historical, app, links, user):
        """One row per old link of ``app``, named by control's ``user``, made through the historical models."""
        return {(model, old): _row(historical, app, model, old, user) for model, old, _new, _column in links}

    def test_it_fills_the_new_links_with_each_control_user_s_person(self, app, name, previous, links):
        historical = _before_the_new_links_take_their_names(app, name, previous)
        ana = get_user_model().objects.create_user(
            username="saas:0199c4b0-0000-7000-8000-00000000a0a0", first_name="Ana", email="ana@example.com"
        )
        rows = self._rows(historical, app, links, ana)

        _migration(app, name).link_hub_users(historical, SimpleNamespace(connection=connection))

        person = HubUser.objects.get(username=ana.username)
        assert (str(person.account_id), person.name, person.email) == (ana.username[5:], "Ana", "ana@example.com")
        for model, old, new, _column in links:
            row = historical.get_model(app, model).objects.get(pk=rows[(model, old)].pk)
            assert getattr(row, f"{new}_id") == person.pk, (model, old)

    def test_a_person_the_database_already_has_is_used_again(self, app, name, previous, links):
        historical = _before_the_new_links_take_their_names(app, name, previous)
        ana = get_user_model().objects.create_user(username="saas:x", first_name="Ana")
        known = HubUser.objects.create(username="saas:x", name="Ana from the photo")
        self._rows(historical, app, links, ana)

        _migration(app, name).link_hub_users(historical, SimpleNamespace(connection=connection))

        assert list(HubUser.objects.values_list("pk", "name")) == [(known.pk, "Ana from the photo")]

    def test_a_hub_s_own_database_has_nothing_to_fill(self, app, name, previous, links, monkeypatch):
        historical = _before_the_new_links_take_their_names(app, name, previous)
        ana = get_user_model().objects.create_user(username="saas:x")
        self._rows(historical, app, links, ana)
        migration = _migration(app, name)
        monkeypatch.setattr(migration.router, "allow_migrate_model", lambda alias, model: False)

        migration.link_hub_users(historical, SimpleNamespace(connection=connection))

        assert not HubUser.objects.exists()

    def test_it_drops_the_old_columns_keys_to_control_s_users(self, app, name, previous, links):
        # A database migrated before W10 has them (phase 1's shared one); this history made the tests' without.
        historical = _before_the_new_links_take_their_names(app, name, previous)
        users = get_user_model()._meta.db_table
        for model, _old, _new, column in links:
            table = historical.get_model(app, model)._meta.db_table
            with connection.cursor() as cursor:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{table}_{column}_w10_fk" FOREIGN KEY ("{column}") '
                    f'REFERENCES "{users}" ("id") DEFERRABLE INITIALLY DEFERRED'
                )

        with connection.schema_editor() as editor:
            _migration(app, name).drop_keys_to_control_users(historical, editor)

        for model, _old, _new, column in links:
            table = historical.get_model(app, model)._meta.db_table
            with connection.cursor() as cursor:
                keys = connection.introspection.get_constraints(cursor, table)
            assert not [
                key for key, details in keys.items() if details["foreign_key"] and details["foreign_key"][0] == users
            ], table

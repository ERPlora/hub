"""Every app fits a hub's own database: the people of the business are its own.

A staff record, its time off, a clock-in, a task, its comments and the WhatsApp inbox's assignments and messages hang
from ``base.HubUser``, never from control's ``auth.User``: a key between two databases does not exist
(``tests/test_guardrails.py``, «(h)»). So every app fits, every vertical's template holds its whole list, and the
expand migrations that moved those links only change the schema: a business's own database holds no control users to
fill them from and no key to them to drop.
"""

import pytest
from django.apps import apps
from django.db import connections

from base import catalog
from base.tenancy import inventory, migrator, names
from base.tenancy.tests import hubs
from base.tests.migration_steps import python_steps
from base.tests.test_auth_views import ON_HUB_A

#: The apps whose links to control's users moved to ``base.HubUser``, and those that waited for them.
PEOPLE_APPS = {"staff", "attendance", "task", "whatsapp_inbox"}
WAITED_FOR_THEM = {"appointment", "online_booking", "service"}

#: Each expand migration: ``(app, migration, [(model, old column, new column)])``.
EXPANDS = [
    ("staff", "0004_hub_users", [("member", "user_id", "hub_user_id"), ("timeoff", "approved_by_id", "approved_by_hub_user_id")]),
    (
        "attendance",
        "0003_hub_users",
        [
            ("record", "created_by_id", "created_by_hub_user_id"),
            ("record", "updated_by_id", "updated_by_hub_user_id"),
            ("correction", "created_by_id", "created_by_hub_user_id"),
            ("attendancesettings", "updated_by_id", "updated_by_hub_user_id"),
        ],
    ),
    ("task", "0002_hub_users", [("task", "created_by_id", "created_by_hub_user_id"), ("comment", "author_id", "author_hub_user_id")]),
    (
        "whatsapp_inbox",
        "0010_hub_users",
        [
            ("conversation", "assigned_to_id", "assigned_to_hub_user_id"),
            ("message", "sent_by_id", "sent_by_hub_user_id"),
            ("note", "author_id", "author_hub_user_id"),
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


def _columns(database, table: str) -> dict[str, bool]:
    """Each column of ``table`` in ``database`` and whether it takes NULL."""
    with database.cursor() as cursor:
        return {column.name: column.null_ok for column in database.introspection.get_table_description(cursor, table)}


def _keys(database, table: str) -> dict[str, str]:
    """The foreign keys of ``table`` in ``database``: the table each column points to."""
    with database.cursor() as cursor:
        constraints = database.introspection.get_constraints(cursor, table)
    return {details["columns"][0]: details["foreign_key"][0] for details in constraints.values() if details["foreign_key"]}


@pytest.mark.parametrize(("app", "name", "links"), EXPANDS, ids=[expand[0] for expand in EXPANDS])
class TestTheExpand:
    """Each expand migration runs on a business's own database, which holds no control users: nothing to fill from
    them and no key to them to drop, so it only changes the schema."""

    pytestmark = ON_HUB_A

    def test_it_runs_no_python(self, app, name, links):
        assert python_steps(f"apps.{app}.migrations.{name}") == []

    def test_the_old_columns_stay_unkeyed_and_the_new_ones_point_to_the_business_s_people(self, app, name, links):
        database = connections[hubs.HUB_A_ALIAS]
        for model, old_column, new_column in links:
            table = apps.get_model(app, model)._meta.db_table
            keys = _keys(database, table)

            assert _columns(database, table)[old_column] is True, (table, old_column)
            assert old_column not in keys, (table, old_column)
            assert keys[new_column] == "base_hubuser", (table, new_column)

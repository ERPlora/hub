"""Control's database as it was before the cut, for the tests of what still reads it that way: ``manage.py
cut_shared_hubs`` copies a business's rows from the tables of the hubs' apps there, and ``control/0007`` renames them.

Before the cut every business kept its rows in control's database. Since then neither production's control nor the
suite's holds those tables, so these tests make them, as the models are today, and write their rows on ``default`` by
name (``Model.objects.using("default")``), never in a business's context.
"""

from django.apps import apps
from django.db import connection

from base.tenancy import inventory


def hub_models() -> list:
    """Every model whose table lives in a hub's database; a model makes its many-to-many tables with its own."""
    return [
        model
        for model in apps.get_models()
        if model._meta.managed and not model._meta.proxy and inventory.classify(model) == inventory.HUB
    ]


def hub_tables() -> set[str]:
    """The names of those tables, the many-to-many ones included."""
    return {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if model._meta.managed and not model._meta.proxy and inventory.classify(model) == inventory.HUB
    }


def hub_tables_sql() -> list[str]:
    """The statements that make every table of the hubs' apps in a database that has none of them."""
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        for model in hub_models():
            editor.create_model(model)
    return editor.collected_sql


def make_hub_tables(on=connection) -> None:
    """The tables of the hubs' apps made in the database of ``on``, a Django connection (control's by default)."""
    with on.cursor() as cursor:
        for statement in hub_tables_sql():
            cursor.execute(statement)


def drop_hub_tables(on=connection) -> None:
    """Those tables dropped again from the database of ``on``, whichever of them it holds."""
    with on.cursor() as cursor:
        for table in sorted(hub_tables()):
            cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


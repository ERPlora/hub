"""The modifier app's migrations: in step with the models, and 0002 (the allergens of an option, MODIFIER-F11) both
ways. Forward, every option the business has gets none; back, the column goes and the options stay. They run on a
business's own database, cloned from the template for each test, through the migrator's alias as ``migrate_hubs`` runs
them."""

import io

from django.core.management import call_command

from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

from .conftest import HUB_DB

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "modifier"
BEFORE = [(APP, "0001_initial")]
AFTER = [(APP, "0002_option_allergens")]
TABLE = "modifier_modifieroption"


@HUB_DB
def test_the_migrations_are_in_step_with_the_models():
    output = io.StringIO()
    call_command("makemigrations", APP, "--check", "--dry-run", stdout=output)
    assert "No changes detected" in output.getvalue()


def options(state, database) -> list:
    return list(state.get_model(APP, "ModifierOption").objects.using(database.alias).order_by("name"))


def test_the_allergens_of_an_option_come_with_0002_and_go_with_its_reverse(database):
    old = migrate(database, BEFORE)
    extras = old.get_model(APP, "ModifierGroup").objects.using(database.alias).create(name="Extras")
    old.get_model(APP, "ModifierOption").objects.using(database.alias).create(group=extras, name="Cheese")
    assert "allergens" not in columns(database, TABLE)

    new = migrate(database, AFTER)
    [cheese] = options(new, database)
    assert ("allergens" in columns(database, TABLE), cheese.allergens) == (True, [])
    cheese.allergens = ["milk"]
    cheese.save(update_fields=["allergens"])

    back = migrate(database, BEFORE)
    assert "allergens" not in columns(database, TABLE)
    assert [option.name for option in options(back, database)] == ["Cheese"]

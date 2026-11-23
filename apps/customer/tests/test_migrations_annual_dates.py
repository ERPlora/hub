"""Migration 0006 of the customer app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, a birthday and an anniversary become the text the card keeps
(``YYYY-MM-DD``, none empty), so a day may then go without its year (``--MM-DD``). Back, a full day is a date again;
a day without its year cannot be one and is left empty."""

from datetime import date

from apps.whatsapp_inbox.tests.test_migrations import database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "customer"
BEFORE = [(APP, "0005_actor_without_address")]
AFTER = [(APP, "0006_annual_dates_as_text")]


def cards(apps, database):
    return apps.get_model(APP, "Customer").objects.using(database.alias)


def days(apps, database) -> list[tuple]:
    return sorted(cards(apps, database).values_list("name", "birthday", "anniversary"))


def test_the_days_go_forward_as_text_and_back_as_dates(database):
    old = migrate(database, BEFORE)
    cards(old, database).create(name="Ana", birthday=date(1990, 3, 14), anniversary=date(2015, 6, 1))
    cards(old, database).create(name="Bea")

    new = migrate(database, AFTER)
    assert days(new, database) == [("Ana", "1990-03-14", "2015-06-01"), ("Bea", "", "")]
    cards(new, database).create(name="Carla", birthday="--03-14", anniversary="2016-02-29")

    old = migrate(database, BEFORE)
    assert days(old, database) == [
        ("Ana", date(1990, 3, 14), date(2015, 6, 1)),
        ("Bea", None, None),
        ("Carla", None, date(2016, 2, 29)),
    ]

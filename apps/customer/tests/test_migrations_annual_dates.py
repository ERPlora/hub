"""Migration 0006 of the customer app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. It writes nothing to the database: a birthday and an anniversary stay
``date`` columns, so the code of before, which keeps running while the deploy migrates (and after a rollback), reads a
day the new code wrote without its year as a date in 1604, and writes its own dates as always."""

from datetime import date

from apps.whatsapp_inbox.tests.test_migrations import database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "customer"
BEFORE = [(APP, "0005_actor_without_address")]
AFTER = [(APP, "0006_annual_dates_without_year")]


def cards(apps, database):
    return apps.get_model(APP, "Customer").objects.using(database.alias)


def days(apps, database) -> list[tuple]:
    return sorted(cards(apps, database).values_list("name", "birthday", "anniversary"))


def test_the_code_of_before_reads_and_writes_the_days_the_new_code_keeps(database):
    old = migrate(database, BEFORE)
    cards(old, database).create(name="Ana", birthday=date(1990, 3, 14))

    new = migrate(database, AFTER)
    cards(new, database).create(name="Lucía", birthday="--03-14", anniversary="2016-02-29")
    assert days(new, database) == [("Ana", "1990-03-14", None), ("Lucía", "--03-14", "2016-02-29")]
    with database.cursor() as cursor:
        cursor.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'customer_customer' "
                       "AND column_name IN ('birthday', 'anniversary')")
        assert {row[0] for row in cursor.fetchall()} == {"date"}
    cards(old, database).create(name="Bea", birthday=date(1985, 7, 1))

    old = migrate(database, BEFORE)
    assert days(old, database) == [
        ("Ana", date(1990, 3, 14), None),
        ("Bea", date(1985, 7, 1), None),
        ("Lucía", date(1604, 3, 14), date(2016, 2, 29)),
    ]

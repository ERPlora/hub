"""Migration 0003 of the table app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, a check saved with the address of a waiter without a name keeps
what goes before the «@» (BASE-F119); a named waiter keeps their name. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "table"
BEFORE = [(APP, "0002_session_table_by_status")]
AFTER = [(APP, "0003_waiter_name_without_address")]


def waiters(apps, database) -> list[str]:
    return sorted(apps.get_model(APP, "TableSession").objects.using(database.alias).values_list("waiter_name", flat=True))


def test_a_waiter_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)
    table = old.get_model(APP, "Table").objects.using(database.alias).create(number="4")
    for waiter in ("bea.lopez@example.com", "Luis García", ""):
        old.get_model(APP, "TableSession").objects.using(database.alias).create(
            table=table, status="closed", waiter_id="7", waiter_name=waiter
        )

    assert waiters(migrate(database, AFTER), database) == ["", "Luis García", "bea.lopez"]
    assert waiters(migrate(database, BEFORE), database) == ["", "Luis García", "bea.lopez"]

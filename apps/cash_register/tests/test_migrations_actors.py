"""Migration 0004 of the cash register, both ways, on a business's own database cloned from the template and through
the migrator's alias, as ``migrate_hubs`` runs it. Forward, whoever the drawer saved by their address (the settings,
a drawer, a shift's opening and closing, a movement, a count) keeps what goes before the «@» (BASE-F119); a named
person keeps their name. Back, nothing changes."""

from django.utils import timezone

from apps.whatsapp_inbox.tests.test_migrations import database, migrate
from base.tests.colleagues import ADDRESS, SHOWN

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "cash_register"
BEFORE = [(APP, "0003_session_people")]
AFTER = [(APP, "0004_actors_without_address")]
NAMED = "Luis García"


def actors(apps, database) -> dict[str, list[str]]:
    def of(model: str, *fields: str) -> list[str]:
        rows = apps.get_model(APP, model).objects.using(database.alias).values_list(*fields)
        return sorted(value for row in rows for value in row)

    return {
        "settings": of("Settings", "updated_by"),
        "drawers": of("Register", "created_by"),
        "shifts": of("Session", "opened_by", "closed_by"),
        "movements": of("Movement", "created_by"),
        "counts": of("Count", "counted_by"),
    }


def test_whoever_the_drawer_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)

    def rows(model: str):
        return old.get_model(APP, model).objects.using(database.alias)

    now = timezone.now()
    rows("Settings").create(updated_by=ADDRESS)
    rows("Register").create(name="Front", created_by=ADDRESS)
    shift, _ = (
        rows("Session").create(
            number=f"S-261122-000{sequence}", business_day=now.date(), sequence=sequence, status="closed",
            opened_by=opened_by, closed_by=closed_by, closed_at=now, expected_balance=0,
        )
        for sequence, opened_by, closed_by in ((1, ADDRESS, NAMED), (2, NAMED, ADDRESS))
    )
    for by in (ADDRESS, NAMED, ""):
        rows("Movement").create(session=shift, type="in", amount=500, created_by=by)
    rows("Count").create(session=shift, total=0, counted_by=ADDRESS)
    cleaned = {
        "settings": [SHOWN],
        "drawers": [SHOWN],
        "shifts": [NAMED, NAMED, SHOWN, SHOWN],
        "movements": ["", NAMED, SHOWN],
        "counts": [SHOWN],
    }

    assert actors(migrate(database, AFTER), database) == cleaned
    assert actors(migrate(database, BEFORE), database) == cleaned

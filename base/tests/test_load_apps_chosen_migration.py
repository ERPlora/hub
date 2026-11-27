"""The businesses set up with a template or a copy before its apps counted as theirs get them chosen (``base/0033``):
every app a load found on or turned on that is still on, being set up or failed, so turning off one of them no longer
takes the others along. Taxes stays as it was: every business is born with it, and it never goes off with another app.
What a load found off or left out, and what no load names, stays as it was. Going back leaves them chosen.
"""

from base.tests.hub_migration import database, migrate

__all__ = ["database"]

BEFORE = [("base", "0032_approval_by_role")]
AFTER = [("base", "0033_apps_turned_on_by_a_load_are_chosen")]


def apps_of(models, alias: str, **given) -> None:
    """The business's rows: ``app=(state, chosen)``."""
    activation = models.get_model("base", "AppActivation").objects.using(alias)
    activation.bulk_create(
        activation.model(host="peluqueria", app=app, state=state, chosen=chosen) for app, (state, chosen) in given.items()
    )


def a_load(models, alias: str, *, undone: bool = False, **statuses) -> None:
    """A load whose report says ``app=status``."""
    from django.utils import timezone

    models.get_model("base", "ImportBatch").objects.using(alias).create(
        name="Peluquería",
        source="catalog",
        template_key="hair_salon.es",
        purpose="template",
        status="complete",
        report={"status": "complete", "apps": [{"id": app, "status": status} for app, status in statuses.items()]},
        undone_at=timezone.now() if undone else None,
    )


def chosen(models, alias: str) -> set[str]:
    rows = models.get_model("base", "AppActivation").objects.using(alias)
    return set(rows.filter(chosen=True).values_list("app", flat=True))


def test_the_apps_a_load_found_on_or_turned_on_are_chosen_and_the_rest_is_left_as_it_was(database):
    alias = database.alias
    old = migrate(database, BEFORE)
    apps_of(
        old,
        alias,
        online_booking=("on", True),
        appointment=("on", False),
        service=("on", False),
        schedule=("creating", False),
        website=("failed", False),
        tax=("on", False),
        table=("on", False),
        customer=("on", False),
        kitchen=("on", False),
        sale=("off", False),
        attendance=("on", False),
    )
    a_load(
        old,
        alias,
        online_booking="empty",
        appointment="empty",
        service="applied",
        schedule="waiting",
        website="setup_failed",
        tax="already",
        table="inactive",
        customer="not_selected",
        kitchen="unknown",
        sale="applied",
    )
    a_load(old, alias, undone=True, attendance="applied")

    new = migrate(database, AFTER)

    assert chosen(new, alias) == {"online_booking", "appointment", "service", "schedule", "website", "attendance"}


def test_a_business_that_never_loaded_anything_keeps_its_apps_as_they_were(database):
    alias = database.alias
    old = migrate(database, BEFORE)
    apps_of(old, alias, online_booking=("on", True), appointment=("on", False))

    new = migrate(database, AFTER)

    assert chosen(new, alias) == {"online_booking"}


def test_going_back_leaves_them_chosen(database):
    alias = database.alias
    old = migrate(database, BEFORE)
    apps_of(old, alias, online_booking=("on", True), appointment=("on", False))
    a_load(old, alias, online_booking="empty", appointment="empty")
    migrate(database, AFTER)

    old = migrate(database, BEFORE)

    assert chosen(old, alias) == {"online_booking", "appointment"}

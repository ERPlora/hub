"""Migration 0006 of the printing app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, who added a printer, changed the settings, set up or retired a
printing device, and asked for a print job, sent it back or cancelled it, saved by the address of an account without a
name, keeps what goes before the «@» (BASE-F119); a person's name and an API key's keep theirs. Back, nothing
changes."""

from apps.whatsapp_inbox.tests.test_migrations import database
from base.tests.colleagues import kept_both_ways

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "printing"
BEFORE = [(APP, "0005_cancel_kitchen_orders_without_printer")]
AFTER = [(APP, "0006_actor_without_address")]
WHO = [
    ("Printer", "created_by"),
    ("PrintDevice", "registered_by"),
    ("PrintDevice", "retired_by"),
    ("PrintJob", "created_by"),
    ("PrintJob", "retried_by"),
    ("PrintJob", "cancelled_by"),
]
#: The settings: one row at most.
SETTINGS = [("Settings", "updated_by")]


def kept_by(apps, database, number: int, who: str) -> None:
    """A printer, a printing device and a print job, all of them by ``who``."""
    rows = {model: apps.get_model(APP, model).objects.using(database.alias) for model, _ in WHO}
    rows["Printer"].create(name=f"Till {number}", kind="system", usage="receipt", created_by=who)
    rows["PrintDevice"].create(name=f"Tablet {number}", registered_by=who, retired_by=who)
    rows["PrintJob"].create(
        job_key=f"job-{number}", usage="receipt", document_type="receipt", created_by=who, retried_by=who, cancelled_by=who
    )


def test_who_printed_or_set_printing_up_saved_by_their_address_keeps_only_what_goes_before_it(database):
    kept_both_ways(database, BEFORE, AFTER, kept_by, WHO, SETTINGS)

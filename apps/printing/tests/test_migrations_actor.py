"""Migration 0006 of the printing app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, who asked for a print job, sent it back or cancelled it, and who
set up a printing device, saved by the address of an account without a name, keep what goes before the «@»
(BASE-F119); a person's name and an API key's keep theirs. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "printing"
BEFORE = [(APP, "0005_cancel_kitchen_orders_without_printer")]
AFTER = [(APP, "0006_actor_without_address")]
SAVED = ("bea.lopez@example.com", "Luis García", "API · orders@shop.example", "")
KEPT = ["", "API · orders@shop.example", "Luis García", "bea.lopez"]
WHO = [("PrintJob", "created_by"), ("PrintJob", "retried_by"), ("PrintJob", "cancelled_by"), ("PrintDevice", "registered_by")]


def written_by(apps, database) -> dict[tuple[str, str], list[str]]:
    rows = {model: apps.get_model(APP, model).objects.using(database.alias) for model, _ in WHO}
    return {(model, field): sorted(rows[model].values_list(field, flat=True)) for model, field in WHO}


def test_who_printed_or_set_up_a_device_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)
    for number, who in enumerate(SAVED):
        old.get_model(APP, "PrintJob").objects.using(database.alias).create(
            job_key=f"job-{number}", usage="receipt", document_type="receipt", created_by=who, retried_by=who, cancelled_by=who
        )
        old.get_model(APP, "PrintDevice").objects.using(database.alias).create(name=f"Till {number}", registered_by=who)

    assert written_by(migrate(database, AFTER), database) == dict.fromkeys(WHO, KEPT)
    assert written_by(migrate(database, BEFORE), database) == dict.fromkeys(WHO, KEPT)

"""Migration 0008 of the service app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, who voided a voucher, adjusted it, spent a session or ended it,
saved by the address of an account without a name, keeps what goes before the «@» (BASE-F119); a person's name and an
API key's keep theirs. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "service"
BEFORE = [(APP, "0007_service_stands_for")]
AFTER = [(APP, "0008_actor_without_address")]
SAVED = ("bea.lopez@example.com", "Luis García", "API · orders@shop.example", "")
KEPT = ["", "API · orders@shop.example", "Luis García", "bea.lopez"]
WHO = [("Grant", "voided_by"), ("GrantAdjustment", "actor"), ("Redemption", "actor"), ("Redemption", "ended_by")]


def written_by(apps, database) -> dict[tuple[str, str], list[str]]:
    rows = {model: apps.get_model(APP, model).objects.using(database.alias) for model, _ in WHO}
    return {(model, field): sorted(rows[model].values_list(field, flat=True)) for model, field in WHO}


def test_who_acted_on_a_voucher_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)
    package = old.get_model(APP, "Package").objects.using(database.alias).create(name="Five cuts")
    lucia = old.get_model("customer", "Customer").objects.using(database.alias).create(name="Lucía Gómez")
    for who in SAVED:
        grant = old.get_model(APP, "Grant").objects.using(database.alias).create(package=package, customer=lucia, voided_by=who)
        old.get_model(APP, "GrantAdjustment").objects.using(database.alias).create(grant=grant, uses_delta=1, reason="A gift", actor=who)
        old.get_model(APP, "Redemption").objects.using(database.alias).create(grant=grant, actor=who, ended_by=who)

    assert written_by(migrate(database, AFTER), database) == dict.fromkeys(WHO, KEPT)
    assert written_by(migrate(database, BEFORE), database) == dict.fromkeys(WHO, KEPT)

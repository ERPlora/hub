"""Migration 0005 of the customer app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, who wrote on a card (its activity, a consent, its health data)
saved by the address of an account without a name keeps what goes before the «@» (BASE-F119); a person's name and an
API key's keep theirs. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "customer"
BEFORE = [(APP, "0004_search_text_without_contact")]
AFTER = [(APP, "0005_actor_without_address")]
SAVED = ("bea.lopez@example.com", "Luis García", "API · orders@shop.example", "")
KEPT = ["", "API · orders@shop.example", "Luis García", "bea.lopez"]
WHO = {"Activity": "actor", "Consent": "recorded_by", "HealthRecord": "updated_by"}


def written_by(apps, database) -> dict[str, list[str]]:
    rows = {model: apps.get_model(APP, model).objects.using(database.alias) for model in WHO}
    return {model: sorted(rows[model].values_list(field, flat=True)) for model, field in WHO.items()}


def test_who_wrote_on_a_card_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)
    for number, who in enumerate(SAVED):
        card = old.get_model(APP, "Customer").objects.using(database.alias).create(name=f"Card {number}")
        old.get_model(APP, "Activity").objects.using(database.alias).create(customer=card, kind="note", actor=who)
        old.get_model(APP, "Consent").objects.using(database.alias).create(customer=card, state="granted", recorded_by=who)
        old.get_model(APP, "HealthRecord").objects.using(database.alias).create(customer=card, updated_by=who)

    assert written_by(migrate(database, AFTER), database) == dict.fromkeys(WHO, KEPT)
    assert written_by(migrate(database, BEFORE), database) == dict.fromkeys(WHO, KEPT)

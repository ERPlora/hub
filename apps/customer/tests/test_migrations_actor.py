"""Migration 0005 of the customer app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, who wrote on a card (its activity, a consent, its health data)
saved by the address of an account without a name keeps what goes before the «@» (BASE-F119); a person's name and an
API key's keep theirs. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database, migrate
from base.tests.colleagues import KEPT, SAVED, written_by

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "customer"
BEFORE = [(APP, "0004_search_text_without_contact")]
AFTER = [(APP, "0005_actor_without_address")]
WHO = [("Activity", "actor"), ("Consent", "recorded_by"), ("HealthRecord", "updated_by")]


def test_who_wrote_on_a_card_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)
    for number, who in enumerate(SAVED):
        card = old.get_model(APP, "Customer").objects.using(database.alias).create(name=f"Card {number}")
        old.get_model(APP, "Activity").objects.using(database.alias).create(customer=card, kind="note", actor=who)
        old.get_model(APP, "Consent").objects.using(database.alias).create(customer=card, state="granted", recorded_by=who)
        old.get_model(APP, "HealthRecord").objects.using(database.alias).create(customer=card, updated_by=who)

    assert written_by(migrate(database, AFTER), database, APP, WHO) == dict.fromkeys(WHO, KEPT)
    assert written_by(migrate(database, BEFORE), database, APP, WHO) == dict.fromkeys(WHO, KEPT)

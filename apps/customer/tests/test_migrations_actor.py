"""Migration 0005 of the customer app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, who wrote on a card (its activity, a consent, its health data)
saved by the address of an account without a name keeps what goes before the «@» (BASE-F119); a person's name and an
API key's keep theirs. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database
from base.tests.colleagues import kept_both_ways

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "customer"
BEFORE = [(APP, "0004_search_text_without_contact")]
AFTER = [(APP, "0005_actor_without_address")]
WHO = [("Activity", "actor"), ("Consent", "recorded_by"), ("HealthRecord", "updated_by")]


def kept_by(apps, database, number: int, who: str) -> None:
    """A card with a line of its activity, a consent and its health data, all of them by ``who``."""
    rows = {model: apps.get_model(APP, model).objects.using(database.alias) for model in ("Customer", *dict(WHO))}
    card = rows["Customer"].create(name=f"Card {number}")
    rows["Activity"].create(customer=card, kind="note", actor=who)
    rows["Consent"].create(customer=card, state="granted", recorded_by=who)
    rows["HealthRecord"].create(customer=card, updated_by=who)


def test_who_wrote_on_a_card_saved_by_their_address_keeps_only_what_goes_before_it(database):
    kept_both_ways(database, BEFORE, AFTER, kept_by, WHO)

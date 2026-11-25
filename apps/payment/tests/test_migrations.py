"""Migration 0005 of the payment app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, whoever Payments saved by their address (who made or changed a
method, who recorded, changed, approved or cancelled a payment) keeps what goes before the «@» (BASE-F119); a named
person keeps their name, and a beneficiary is not a colleague. Back, nothing changes."""

import datetime as dt

from apps.whatsapp_inbox.tests.test_migrations import database, migrate
from base.tests.colleagues import ADDRESS, SHOWN

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "payment"
BEFORE = [(APP, "0004_payment_currency_without_default")]
AFTER = [(APP, "0005_actors_without_address")]
NAMED = "Luis García"
ACTORS = ("created_by", "updated_by", "approved_by", "cancelled_by")


def saved(apps, database) -> dict[str, list]:
    def rows(model: str):
        return apps.get_model(APP, model).objects.using(database.alias)

    return {
        "methods": sorted(rows("PaymentMethod").values_list("created_by", "updated_by")),
        "payments": sorted(rows("Payment").values_list("beneficiary_name", *ACTORS)),
    }


def test_whoever_payments_saved_by_their_address_keeps_only_what_goes_before_it(database):
    old = migrate(database, BEFORE)

    def rows(model: str):
        return old.get_model(APP, model).objects.using(database.alias)

    method = rows("PaymentMethod").create(name="Bank", created_by=ADDRESS, updated_by=NAMED)
    rows("PaymentMethod").create(name="Cash", created_by=NAMED, updated_by=ADDRESS)
    common = {"method": method, "payment_date": dt.date(2026, 11, 22), "amount": 1000, "currency": "EUR"}
    rows("Payment").create(
        reference="PAY-1", beneficiary_name=ADDRESS, created_by=ADDRESS, updated_by=ADDRESS, approved_by=ADDRESS, **common
    )
    rows("Payment").create(reference="PAY-2", beneficiary_name="Florist", created_by=NAMED, cancelled_by=ADDRESS, **common)
    cleaned = {
        "methods": [(NAMED, SHOWN), (SHOWN, NAMED)],
        "payments": [("Florist", NAMED, "", "", SHOWN), (ADDRESS, SHOWN, SHOWN, SHOWN, "")],
    }

    assert saved(migrate(database, AFTER), database) == cleaned
    assert saved(migrate(database, BEFORE), database) == cleaned

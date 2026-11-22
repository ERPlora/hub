"""Migration 0008 of the service app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, who made or changed the catalog, sold, voided or adjusted a
voucher, spent a session or ended it, saved by the address of an account without a name, keeps what goes before the
«@» (BASE-F119); a person's name and an API key's keep theirs. Back, nothing changes."""

from apps.whatsapp_inbox.tests.test_migrations import database
from base.tests.colleagues import kept_both_ways

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "service"
BEFORE = [(APP, "0007_service_stands_for")]
AFTER = [(APP, "0008_actor_without_address")]
WHO = [
    ("Category", "created_by"),
    ("Category", "updated_by"),
    ("Service", "created_by"),
    ("Service", "updated_by"),
    ("Package", "created_by"),
    ("Package", "updated_by"),
    ("Grant", "created_by"),
    ("Grant", "voided_by"),
    ("GrantAdjustment", "actor"),
    ("Redemption", "actor"),
    ("Redemption", "ended_by"),
]
#: The settings: one row at most.
SETTINGS = [("ServiceSettings", "updated_by")]


def kept_by(apps, database, number: int, who: str) -> None:
    """A category, a service, a package and a voucher of it, adjusted and spent, all of them by ``who``."""
    rows = {model: apps.get_model(APP, model).objects.using(database.alias) for model, _ in WHO}
    customer = apps.get_model("customer", "Customer").objects.using(database.alias).create(name=f"Lucía {number}")
    made = {"created_by": who, "updated_by": who}
    rows["Category"].create(name=f"Hair {number}", **made)
    rows["Service"].create(name=f"Haircut {number}", **made)
    package = rows["Package"].create(name=f"Five cuts {number}", **made)
    grant = rows["Grant"].create(package=package, customer=customer, created_by=who, voided_by=who)
    rows["GrantAdjustment"].create(grant=grant, uses_delta=1, reason="A gift", actor=who)
    rows["Redemption"].create(grant=grant, actor=who, ended_by=who)


def test_who_acted_on_the_catalog_or_a_voucher_saved_by_their_address_keeps_only_what_goes_before_it(database):
    kept_both_ways(database, BEFORE, AFTER, kept_by, WHO, SETTINGS)

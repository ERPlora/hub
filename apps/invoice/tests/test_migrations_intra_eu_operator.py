"""Migration 0007 of the invoice app, both ways, on a business's own database cloned from the template and through the
migrator's alias, as ``migrate_hubs`` runs it. Forward, the issuer kept before it is not registered for intra-EU
operations (its documents print as before); back, the columns go and the issuer stays."""

from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "invoice"
BEFORE = [(APP, "0006_customer_id_type_choices")]
AFTER = [(APP, "0007_issuer_intra_eu_operator")]


def issuers(state, database) -> list[str]:
    return list(state.get_model(APP, "Issuer").objects.using(database.alias).values_list("legal_name", flat=True))


def test_the_intra_eu_mark_comes_off_with_0007_and_goes_with_its_reverse(database):
    old = migrate(database, BEFORE)
    old.get_model(APP, "Issuer").objects.using(database.alias).create(
        legal_name="Peluquería Ana SL", tax_id="B12345674", address="Calle Mayor 1"
    )
    assert "intra_eu_operator" not in columns(database, "invoice_issuer")

    new = migrate(database, AFTER)
    [issuer] = new.get_model(APP, "Issuer").objects.using(database.alias).all()
    assert issuer.intra_eu_operator is False
    assert "issuer_intra_eu_operator" in columns(database, "invoice_invoice")

    back = migrate(database, BEFORE)
    assert "intra_eu_operator" not in columns(database, "invoice_issuer")
    assert "issuer_intra_eu_operator" not in columns(database, "invoice_invoice")
    assert issuers(back, database) == ["Peluquería Ana SL"]

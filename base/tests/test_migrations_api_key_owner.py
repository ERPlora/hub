"""Migration 0026 of base, both ways, on a business's own database cloned from the template and through the migrator's
alias, as ``migrate_hubs`` runs it. Forward, every key is kept and gains who made it, empty until the next photo names
the owner (BASE-F125); back, the column goes and the keys stay."""

from apps.whatsapp_inbox.tests.test_migrations import columns, database, migrate

#: The fixture taken from the inbox's migration tests: a business's database cloned from the template.
__all__ = ["database"]

APP = "base"
BEFORE = [(APP, "0025_membership_accountant_role")]
AFTER = [(APP, "0026_api_key_owner")]


def a_key(apps, database, name: str):
    return apps.get_model(APP, "ApiKey").objects.using(database.alias).create(
        name=name, prefix="erpk_live_ab12cd34", token_digest=name.ljust(64, "0"), mode="full"
    )


def test_the_keys_go_forward_with_no_maker_yet_and_back_without_the_column(database):
    a_key(migrate(database, BEFORE), database, "shop")

    new = migrate(database, AFTER)
    assert "owner_id" in columns(database, "base_apikey")
    keys = new.get_model(APP, "ApiKey").objects.using(database.alias)
    assert list(keys.values_list("name", "owner_id")) == [("shop", None)]
    maker = new.get_model(APP, "HubUser").objects.using(database.alias).create(username="saas:olga")
    keys.update(owner=maker)

    old = migrate(database, BEFORE)
    assert "owner_id" not in columns(database, "base_apikey")
    assert list(old.get_model(APP, "ApiKey").objects.using(database.alias).values_list("name", flat=True)) == ["shop"]

    again = migrate(database, AFTER)
    assert list(again.get_model(APP, "ApiKey").objects.using(database.alias).values_list("owner_id", flat=True)) == [None]

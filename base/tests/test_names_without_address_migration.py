"""Migration 0034 of base: a name kept as an address keeps only what goes before the «@» (BASE-F119).

erplora.com names an account without a name by its address, and the Hub copied it as the person's name: on control's
copy of the account, on the business's person, on «My profile» and on a visit of ERPlora's support. Forward, each bare address keeps what goes before
its «@»; a person's name keeps theirs. Back, nothing changes."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import DEFAULT_DB_ALIAS, connection, router

from base.tests.colleagues import KEPT, SAVED, kept_both_ways
from base.tests.hub_migration import database

__all__ = ["database"]

BEFORE = [("base", "0033_apps_turned_on_by_a_load_are_chosen")]
AFTER = [("base", "0034_names_without_address")]
MIGRATION = import_module("base.migrations.0034_names_without_address")


def kept_by(apps, database, number: int, who: str) -> None:
    """The person ``number`` of the business, named ``who`` on the business and in «My profile», and a visit of
    support by someone named ``who``."""
    username = f"saas:{number}"
    apps.get_model("base", "HubUser").objects.using(database.alias).create(username=username, name=who)
    apps.get_model("base", "Profile").objects.using(database.alias).create(username=username, first_name=who)
    apps.get_model("base", "SupportVisit").objects.using(database.alias).create(username=username, name=who)


def test_a_person_of_the_business_named_by_their_address_keeps_only_what_goes_before_it(database):
    kept_both_ways(
        database, BEFORE, AFTER, kept_by, [("HubUser", "name"), ("Profile", "first_name"), ("SupportVisit", "name")]
    )


@pytest.mark.django_db
def test_an_account_named_by_its_address_on_control_keeps_only_what_goes_before_it():
    accounts = get_user_model().objects
    for number, who in enumerate(SAVED):
        accounts.create_user(f"saas:{number}", first_name=who)
    MIGRATION.accounts_without_address(django_apps, SimpleNamespace(connection=connection))
    assert sorted(accounts.values_list("first_name", flat=True)) == KEPT


def test_the_accounts_are_cut_on_control_where_they_live():
    on_control = [op for op in MIGRATION.Migration.operations if op.code is MIGRATION.accounts_without_address]
    assert [router.allow_migrate(DEFAULT_DB_ALIAS, "base", **op.hints) for op in on_control] == [True]

"""Writes of the price lists (WORKBOOK PRICING-F02 to F05): create, edit, make one the general list, deactivate and
activate it. A refusal writes nothing and records no event."""

import datetime as dt

from live.errors import Conflict, InvalidPayload, PermissionDenied

from apps.pricing.models import PriceList

from .conftest import HUB_DB, make_group, make_list
from .test_services import events, no_events, refused, run

pytestmark = HUB_DB


# Price lists: create (F02)


def test_a_list_is_created_active_with_its_group_by_name_and_announced():
    vip = make_group("VIP")
    row = run(
        "pricing.price_list.create",
        {"code": "VIP", "name": "VIP members", "customer_group": "vip", "tax_included": True, "valid_from": "2026-07-01"},
        actor="ana",
    )
    assert (row.code, row.customer_group_id, row.customer_group_name, row.is_active, row.item_count) == (
        "VIP",
        vip.id,
        "VIP",
        True,
        0,
    )
    stored = PriceList.objects.get()
    assert (stored.created_by, stored.updated_by, stored.valid_from) == ("ana", "ana", dt.date(2026, 7, 1))
    assert events("pricing.price_list.created") == [{"id": str(row.id), "code": "VIP", "is_default": False}]


def test_a_repeated_code_is_refused_under_code_whatever_its_case_also_an_inactive_list():
    make_list("VIP", is_active=False)
    error = refused(Conflict, "pricing.price_list.create", {"code": "vip", "name": "Again"})
    assert (error.code, error.fields) == (
        "pricing.duplicate_code",
        {"code": "A price list with that code already exists. Pick a different code."},
    )
    assert PriceList.objects.count() == 1 and no_events()


def test_a_new_general_list_takes_the_mark_from_the_old_one():
    old = make_list("OLD", is_default=True)
    row = run("pricing.price_list.create", {"code": "NEW", "name": "New", "is_default": True})
    old.refresh_from_db()
    assert (row.is_default, old.is_default) == (True, False)
    assert events("pricing.price_list.default_changed") == [{"id": str(row.id), "is_default": True, "previous_id": str(old.id)}]


def test_a_manager_creates_and_an_employee_does_not():
    run("pricing.price_list.create", {"code": "M", "name": "M"}, role="hub_manager")
    refused(PermissionDenied, "pricing.price_list.create", {"code": "E", "name": "E"}, role="hub_employee")


# Price lists: edit (F03)


def test_an_edit_changes_only_what_is_sent_and_says_so_once():
    vip = make_group("VIP")
    price_list = make_list("VIP", "VIP", customer_group_id=vip.id, currency="EUR")
    row = run("pricing.price_list.update", {"price_list": "VIP", "name": "VIP members", "valid_until": "2026-12-31"})
    assert (row.name, row.customer_group_id, row.valid_until) == ("VIP members", vip.id, dt.date(2026, 12, 31))
    assert events("pricing.price_list.updated") == [{"id": str(price_list.id)}]
    run("pricing.price_list.update", {"id": str(price_list.id), "name": "VIP members"})
    assert len(events("pricing.price_list.updated")) == 1
    cleared = run("pricing.price_list.update", {"id": str(price_list.id), "customer_group_id": None, "tax_included": None})
    assert (cleared.customer_group_id, cleared.tax_included) == (None, None)


def test_an_edit_keeps_the_rules_of_a_list():
    general = make_list("GEN", is_default=True)
    vip = make_group("VIP")
    error = refused(InvalidPayload, "pricing.price_list.update", {"id": str(general.id), "customer_group": "VIP"})
    assert error.fields == {"customer_group": "The general list is for everybody: take its customer group off."}
    dated = make_list("DATED", valid_from=dt.date(2026, 7, 10))
    error = refused(InvalidPayload, "pricing.price_list.update", {"id": str(dated.id), "valid_until": "2026-07-01"})
    assert set(error.fields) == {"valid_until"}
    make_list("TAKEN")
    error = refused(Conflict, "pricing.price_list.update", {"id": str(dated.id), "code": "taken"})
    assert error.code == "pricing.duplicate_code"
    assert vip.id and no_events()


# Price lists: the general one (F04)


def test_making_a_list_general_takes_the_mark_from_the_old_one():
    old = make_list("OLD", is_default=True)
    new = make_list("NEW")
    row = run("pricing.price_list.set_default", {"price_list": "NEW"})
    old.refresh_from_db()
    assert (row.is_default, old.is_default) == (True, False)
    assert events("pricing.price_list.default_changed") == [{"id": str(new.id), "is_default": True, "previous_id": str(old.id)}]
    # Again: nothing changes, nothing is said.
    run("pricing.price_list.set_default", {"price_list": "NEW"})
    assert len(events("pricing.price_list.default_changed")) == 1


def test_the_mark_can_be_taken_off():
    general = make_list("GEN", is_default=True)
    row = run("pricing.price_list.set_default", {"id": str(general.id), "is_default": False})
    assert row.is_default is False
    assert events("pricing.price_list.default_changed") == [{"id": str(general.id), "is_default": False, "previous_id": None}]


def test_an_inactive_list_or_one_with_a_group_is_never_general():
    make_list("OFF", is_active=False)
    make_list("VIP", customer_group_id=make_group().id)
    assert refused(Conflict, "pricing.price_list.set_default", {"price_list": "OFF"}).code == "pricing.price_list_inactive"
    assert refused(Conflict, "pricing.price_list.set_default", {"price_list": "VIP"}).code == "pricing.default_has_group"
    assert no_events()


def test_a_general_list_that_keeps_losing_the_race_is_refused_with_its_code(monkeypatch):
    # Another choice wins every try (here: the old general list is never unmarked): a 409 with a stable
    # code, never the database's IntegrityError (a 500).
    from apps.pricing.services import price_lists

    make_list("OLD", is_default=True)
    make_list("NEW")
    monkeypatch.setattr(price_lists, "_take_default_mark", lambda price_list: None)
    error = refused(Conflict, "pricing.price_list.set_default", {"price_list": "NEW"})
    assert error.code == "pricing.default_busy"
    assert PriceList.objects.get(is_default=True).code == "OLD" and no_events()


def test_the_general_list_is_in_the_business_s_currency():
    # A general list in dollars would never apply: the till sells in the business's currency (here, euros).
    error = refused(InvalidPayload, "pricing.price_list.create", {"code": "USD", "name": "USD", "currency": "USD", "is_default": True})
    assert set(error.fields) == {"is_default"} and not PriceList.objects.filter(code="USD").exists()
    make_list("DOLLARS", currency="USD")
    assert refused(Conflict, "pricing.price_list.set_default", {"price_list": "DOLLARS"}).code == "pricing.default_currency"
    make_list("GEN", is_default=True)
    error = refused(InvalidPayload, "pricing.price_list.update", {"price_list": "GEN", "currency": "USD"})
    assert set(error.fields) == {"currency"}
    assert PriceList.objects.get(code="GEN").currency == "EUR" and no_events()


# Price lists: deactivate and activate (F05)


def test_a_list_is_deactivated_and_activated_again_but_never_the_general_one():
    price_list = make_list("SUMMER")
    assert run("pricing.price_list.deactivate", {"price_list": "summer"}).is_active is False
    assert refused(Conflict, "pricing.price_list.deactivate", {"price_list": "summer"}).code == (
        "pricing.price_list_already_inactive"
    )
    assert run("pricing.price_list.activate", {"price_list": "summer"}).is_active is True
    assert refused(Conflict, "pricing.price_list.activate", {"price_list": "summer"}).code == "pricing.price_list_already_active"
    assert events("pricing.price_list.deactivated") == [{"id": str(price_list.id)}]
    assert events("pricing.price_list.activated") == [{"id": str(price_list.id)}]
    make_list("GEN", is_default=True)
    error = refused(Conflict, "pricing.price_list.deactivate", {"price_list": "GEN"})
    assert error.code == "pricing.price_list_is_default"

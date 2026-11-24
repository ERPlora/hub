"""What an API key may do on an app: read, create, update and delete (``base.api_actions``).

A key's permissions are ``{app | "*": [actions]}``. A query of an app is ``read``; a command is ``create``, ``update`` or
``delete`` by the verb that ends its name, from a closed table: a command whose verb is not in it resolves to nothing,
so no key opens it until someone decides what it is.
"""

from types import SimpleNamespace

import pytest
from live.operations import registry

from base import api_actions
from base.api_actions import CREATE, DELETE, READ, UPDATE


def op(name: str, kind: str = "command"):
    return SimpleNamespace(name=name, kind=kind, app_label=name.split(".")[0])


def test_every_published_operation_resolves_to_an_action():
    unresolved = sorted(each.name for each in registry.values() if each.expose_api and api_actions.action_of(each) is None)
    assert unresolved == [], (
        "A published command whose verb is not in base.api_actions' table opens to no API key: put its verb in "
        f"CREATE_VERBS, UPDATE_VERBS or DELETE_VERBS: {unresolved}"
    )


def test_a_query_is_read_whatever_its_verb():
    assert api_actions.action_of(op("tax.category.delete_preview", kind="query")) == READ


@pytest.mark.parametrize(
    ("name", "action"),
    [
        ("customer.customer.create", CREATE),
        ("cash_register.movement.add", CREATE),
        ("inventory.product.bulk_create", CREATE),
        ("base.file.upload", CREATE),
        ("base.file.create_folder", CREATE),
        ("customer.customer.update", UPDATE),
        ("appointment.appointment.cancel", UPDATE),
        ("service.grant.void", UPDATE),
        ("inventory.product.upload_image", UPDATE),
        ("sale.order.note_bill", UPDATE),
        ("customer.customer.delete", DELETE),
        ("pricing.price_item.remove", DELETE),
        ("appointment.appointment.bulk_delete", DELETE),
        ("cart_checkout.customer.erase", DELETE),
    ],
)
def test_a_command_is_what_its_verb_says(name, action):
    assert api_actions.action_of(op(name)) == action


def test_a_command_with_a_verb_nobody_decided_resolves_to_nothing():
    assert api_actions.action_of(op("customer.customer.frobnicate")) is None


def test_the_three_tables_never_share_a_verb():
    tables = (api_actions.CREATE_VERBS, api_actions.UPDATE_VERBS, api_actions.DELETE_VERBS)
    assert sum(len(table) for table in tables) == len(set().union(*tables))


class TestAllows:
    def test_an_app_s_actions_reach_that_app_only(self):
        scopes = {"customer": [READ, CREATE]}
        assert api_actions.allows(scopes, "customer", READ)
        assert api_actions.allows(scopes, "customer", CREATE)
        assert not api_actions.allows(scopes, "customer", UPDATE)
        assert not api_actions.allows(scopes, "tax", READ)

    def test_every_app_reaches_any_app_with_its_actions(self):
        scopes = {"*": [READ]}
        assert api_actions.allows(scopes, "customer", READ)
        assert api_actions.allows(scopes, "tax", READ)
        assert not api_actions.allows(scopes, "tax", DELETE)

    def test_every_app_and_one_app_add_up(self):
        scopes = {"*": [READ], "customer": [DELETE]}
        assert api_actions.allows(scopes, "customer", DELETE)
        assert not api_actions.allows(scopes, "tax", DELETE)

    @pytest.mark.parametrize("scopes", [{}, None, [], {"customer": "read"}, {"*": None}])
    def test_nothing_or_a_broken_shape_allows_nothing(self, scopes):
        assert not api_actions.allows(scopes, "customer", READ)

    def test_an_action_nobody_decided_is_never_allowed(self):
        assert not api_actions.allows({"*": list(api_actions.ACTIONS)}, "customer", None)


@pytest.mark.parametrize(
    ("scopes", "kept"),
    [
        ({"customer": [DELETE, READ, DELETE]}, {"customer": [READ, DELETE]}),
        ({"*": [READ], "tax": []}, {"*": [READ]}),
        ({"tax": ["read", "write"]}, {"tax": [READ]}),
        ({"tax": ["write"]}, {}),
        ({"tax": "read"}, {}),
        (None, {}),
    ],
)
def test_a_key_s_actions_are_kept_in_their_order_and_only_actions(scopes, kept):
    assert api_actions.normalised(scopes) == kept

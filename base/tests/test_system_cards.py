"""The cards an app puts in System (hub#683: the old hub's «Your printer» in Resources)."""

from types import SimpleNamespace

import pytest

from base import home


def carded(*cards, permissions=("things.view",), path="/nowhere"):
    return SimpleNamespace(
        label="things", path=path, permissions=dict.fromkeys(permissions, "A phrase"), system_cards=list(cards)
    )


def person(*permissions):
    from live.context import OperationContext, Scope

    return OperationContext(scope=Scope("host", "a"), actor="ana", permissions=frozenset(permissions), language="en")


def test_a_card_is_its_apps_component_named_by_the_app():
    card = {"key": "printer", "component": "ThingsCard"}

    assert home.system_cards.system_cards(person(), [carded(card)]) == [
        {"key": "things.printer", "app": "things", "component": "ThingsCard"}
    ]


def test_an_app_that_declares_no_card_brings_none():
    assert home.system_cards.system_cards(person(), [SimpleNamespace(label="things")]) == []


def test_a_card_with_a_permission_only_for_whoever_has_it_in_the_order_declared():
    first = {"key": "printer", "component": "ThingsCard", "permission": "things.view"}
    second = {"key": "drawer", "component": "DrawerCard"}

    assert [card["key"] for card in home.system_cards.system_cards(person(), [carded(first, second)])] == ["things.drawer"]
    assert [card["key"] for card in home.system_cards.system_cards(person("things.view"), [carded(first, second)])] == [
        "things.printer",
        "things.drawer",
    ]


@pytest.fixture
def components(tmp_path):
    """An app's folder with ``frontend/components/ThingsCard.vue``."""
    folder = tmp_path / "frontend" / "components"
    folder.mkdir(parents=True)
    (folder / "ThingsCard.vue").write_text("<template><p /></template>\n")
    return tmp_path


@pytest.mark.parametrize(
    ("cards", "errors"),
    [
        (None, 0),
        ([], 0),
        ([{"key": "printer", "component": "ThingsCard"}], 0),
        ([{"key": "printer", "component": "ThingsCard", "permission": "things.view"}], 0),
        ({"key": "printer", "component": "ThingsCard"}, 1),  # one card, not a list of them
        (["ThingsCard"], 1),
        ([{"component": "ThingsCard"}], 1),  # no key
        ([{"key": "", "component": "ThingsCard"}], 1),
        ([{"key": "printer"}], 1),  # no component
        ([{"key": "printer", "component": "MissingCard"}], 1),  # no such file: the card would never mount
        ([{"key": "printer", "component": "../ThingsCard"}], 1),  # a name, never a path
        ([{"key": "printer", "component": "../components/ThingsCard"}], 1),  # a file, but the SPA would never mount it
        ([{"key": "printer", "component": "ThingsCard", "permission": "other.view"}], 1),  # not the app's
        ([{"key": "printer", "component": "ThingsCard", "permision": "things.view"}], 1),  # a field misspelt
        ([{"key": "printer", "component": "ThingsCard"}, {"key": "printer", "component": "ThingsCard"}], 1),
    ],
)
def test_what_an_app_declares_as_its_cards_is_checked_at_start(components, cards, errors):
    declared = SimpleNamespace(label="things", path=str(components), permissions={"things.view": "See the things"})
    if cards is not None:
        declared.system_cards = cards

    found = home.system_cards.system_card_errors([declared])

    assert len(found) == errors
    assert all(error.id == "base.E015" for error in found)


def test_the_check_of_the_cards_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.system_cards.all_live_app_configs", lambda: [carded({"key": "printer"})])

    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E015"] == ["base.E015"]

"""The assistant's cards for removing devices (BASE-F70, BASE-F71).

- «Remove the unused» says, under «What will happen», how many devices it removes and which ones, never the one in
  hand; with none to remove there is no card, and the model hears why.
- «Remove this device» says when the device was last used: two devices without a name read the same («Chrome ·
  Linux») and only their last use tells them apart; and, for the one in hand, what «Devices» says of it: removing it
  closes the person's session.
"""

import datetime as dt
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.test import RequestFactory
from django.utils import timezone
from live import assistant as shared
from live.context import OperationContext
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.ninja import operation_ids
from live.operations import get

from base import access
from base.models.access import TrustedDevice
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests import card_turn
from base.tests.card_turn import call
from config.api import api

__all__ = ["in_business_a"]

pytestmark = HUB_DB

ADMIN = frozenset({"base.view_home", "base.administer_hub"})
ASK = "Clear out the old devices nobody uses any more, but keep this one."
PRUNE_LABELS = {"en": ("Devices to remove", "Which"), "es": ("Dispositivos que se quitan", "Cuáles")}
NOTHING_TO_REMOVE = {
    "en": "No device has gone 30 days without being used, so there is nothing to remove.",
    "es": "Ningún dispositivo lleva 30 días sin usarse, así que no hay nada que quitar.",
}
LAST_USE = {"en": ("Last used", "Nov 22, 2026, 4:18\u202fPM"), "es": ("Último uso", "22 nov 2026, 16:18")}
FRONTEND = Path(apps.get_app_config("base").path) / "frontend/locale"
#: What «Devices» says before removing the device in hand, in each language.
REMOVE_YOURS = {
    language: json.loads((FRONTEND / f"{language}.json").read_text())["base"]["devices"]["removeYours"]
    for language in ("en", "es")
}


def a_device(days_ago: float = 0, **fields) -> tuple[TrustedDevice, str]:
    token = access.new_device_token()
    fields.setdefault("last_entry_at", timezone.now() - dt.timedelta(days=days_ago))
    device = TrustedDevice.objects.create(token_digest=access.token_digest(token), mode=access.SHARED, **fields)
    return device, token


def turn(token: str, pending: dict, *, language: str = "en", decision: dict | None = None) -> dict:
    """A turn of the assistant asked from the device whose cookie is ``token`` (the one in hand)."""
    request = RequestFactory().get("/")
    request.COOKIES[access.DEVICE_COOKIE] = token
    context = OperationContext(scope=A, actor="ana", permissions=ADMIN, language=language, request=request)
    return card_turn.turn(context, pending, said=ASK, decision=decision)


def preview_lines(card: dict) -> list[tuple]:
    return [(field["name"], field["label"], field["value"]) for field in card["preview"]]


@pytest.mark.parametrize("language", ["en", "es"])
def test_clearing_out_the_unused_devices_says_how_many_and_which_it_removes(language):
    _, in_hand = a_device(days_ago=90)
    a_device(days_ago=40, name="Bar")
    a_device(days_ago=35, agent="Chrome · Linux")
    a_device(days_ago=0, name="Kitchen")
    card = turn(in_hand, call("base.device.prune", {}), language=language)["confirm"]
    how_many, which = PRUNE_LABELS[language]
    assert preview_lines(card) == [("count", how_many, 2), ("devices", which, ["Chrome · Linux", "Bar"])]
    assert card["preview"][1]["named"] is True


@pytest.mark.parametrize("language", ["en", "es"])
def test_with_no_device_unused_for_30_days_there_is_no_card_and_the_model_hears_why(language):
    _, in_hand = a_device(days_ago=90)
    a_device(days_ago=0, agent="Chrome · Linux")
    plan = turn(in_hand, call("base.device.prune", {}), language=language)
    assert (plan["confirm"], plan["pending"], plan["executed"]) == (None, [], [])
    told = json.loads(plan["append"][0]["content"])["error"]
    assert (told["code"], told["message"]) == ("base.no_unused_devices", NOTHING_TO_REMOVE[language])


def test_the_yes_removes_the_devices_its_card_showed_and_keeps_the_one_in_hand():
    here, in_hand = a_device(days_ago=90)
    a_device(days_ago=40, name="Bar")
    kept, _ = a_device(days_ago=0, name="Kitchen")
    drawn = turn(in_hand, call("base.device.prune", {}))
    plan = turn(in_hand, drawn["pending"][0], decision={"call_id": "c1", "accepted": True, "typed": "CONFIRM"})
    assert plan["executed"][0]["outcome"] == "ok"
    assert set(TrustedDevice.objects.values_list("pk", flat=True)) == {here.pk, kept.pk}


@pytest.mark.parametrize("language", ["en", "es"])
def test_removing_one_of_two_devices_with_the_same_name_says_when_it_was_last_used(language):
    _, in_hand = a_device(days_ago=0, name="Office laptop")
    lost, _ = a_device(agent="Chrome · Linux", last_entry_at=dt.datetime(2026, 11, 22, 15, 18, tzinfo=dt.UTC))
    a_device(agent="Chrome · Linux", last_entry_at=dt.datetime(2026, 11, 20, 9, 5, tzinfo=dt.UTC))
    card = turn(in_hand, call("base.device.remove", {"id": str(lost.pk)}), language=language)["confirm"]
    assert [field["value"] for field in card["fields"]] == ["Chrome · Linux"]
    label, when = LAST_USE[language]
    assert preview_lines(card) == [("last_entry_at", label, when)]


@pytest.mark.parametrize("language", ["en", "es"])
def test_removing_the_device_in_hand_says_as_devices_does_that_it_closes_the_persons_session(language):
    here, in_hand = a_device(days_ago=0, name="Bar")
    card = turn(in_hand, call("base.device.remove", {"id": str(here.pk)}), language=language)["confirm"]
    [last_use, yours] = card["preview"]
    assert last_use["name"] == "last_entry_at"
    assert yours["titled"] is True
    assert f"{yours['label']}: {yours['value']}" == REMOVE_YOURS[language]


@pytest.mark.parametrize("read", ["base.device.unused", "base.device.removal"])
def test_the_read_behind_the_card_is_not_a_tool_of_the_assistant(read):
    assert not shared.is_tool(get(read))


@pytest.mark.parametrize("read", ["base.device.unused", "base.device.removal"])
def test_the_read_behind_the_card_is_only_for_who_administers_the_business_and_only_on_the_card(read):
    """It says which devices the business has and when they were used: no route of the API and no live query serve
    it, and run as someone who cannot administer the business it refuses."""
    op = get(read)
    assert read not in operation_ids(api)
    assert not live_registry.is_subscribable(read)
    device, _ = a_device(days_ago=90)
    data = {"id": device.pk} if "id" in op.input.model_fields else {}
    someone = OperationContext(scope=A, actor="leo", permissions=frozenset({"base.view_home"}))
    with pytest.raises(PermissionDenied):
        op(someone, op.input(**data))


def test_a_yes_to_a_card_whose_devices_changed_removes_nothing_and_draws_the_card_again():
    _, in_hand = a_device(days_ago=90)
    a_device(days_ago=40, name="Bar")
    drawn = turn(in_hand, call("base.device.prune", {}))
    a_device(days_ago=35, name="Terrace")
    plan = turn(in_hand, drawn["pending"][0], decision={"call_id": "c1", "accepted": True, "typed": "CONFIRM"})
    assert plan["executed"] == []
    assert preview_lines(plan["confirm"])[1][2] == ["Terrace", "Bar"]
    assert TrustedDevice.objects.count() == 3

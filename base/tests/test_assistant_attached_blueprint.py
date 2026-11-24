"""The copy of another business attached in the assistant's chat (a ``.blueprint.zip``) loads with
``base.blueprint.import``, its card and the person's yes, as Settings › Data › Import loads it: the model names the file
and the Hub gives the operation the file the person attached, never what the model writes."""

import json

import pytest
from live import assistant as shared
from live.operations import get

from base.models import Membership
from base.models.blueprints import ImportBatch
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import asked, turn
from base.tests.test_services_data import a_file, person

__all__ = ["in_business_a"]

pytestmark = HUB_DB

NAME = "bar-pepe.blueprint.zip"


@pytest.fixture
def owner():
    return person(Membership.Role.OWNER)


def attaching(data: str) -> dict:
    file = {"type": "input_file", "filename": NAME, "mime_type": "application/zip", "data": data}
    return {"role": "user", "content": [{"type": "text", "text": "cárgame la copia de otro bar"}, file]}


def load_call() -> dict:
    return {"call_id": "c1", "name": shared.tool_name("base.blueprint.import"), "arguments": json.dumps({"file_base64": NAME})}


def test_the_copy_goes_to_the_gateway_by_its_name_only(owner):
    copy = a_file()

    plan = turn(owner, [attaching(copy)], [])

    sent = json.dumps(plan["messages"])
    assert NAME in sent
    assert copy not in sent
    # Nor in the rounds after: the panel sends the whole conversation again with each question.
    later = [attaching(copy), {"role": "assistant", "content": "¿La cargo?"}, {"role": "user", "content": "sí, cárgala"}]
    assert copy not in json.dumps(turn(owner, later, [])["messages"])


def test_a_copy_attached_in_the_chat_loads_with_its_card_and_the_persons_yes(owner):
    messages = [attaching(a_file()), asked(load_call())]

    drawn = turn(owner, messages, [load_call()])

    card = drawn["confirm"]
    assert card["operation"] == "base.blueprint.import"
    assert [field["value"] for field in card["fields"] if field["name"] == "file_base64"] == [NAME]
    assert not ImportBatch.objects.exists()

    yes = {"call_id": "c1", "accepted": True, "typed": card["confirm_word"]}
    done = turn(owner, messages, drawn["pending"], decision=yes)

    assert [(row["name"], row["outcome"]) for row in done["executed"]] == [("base.blueprint.import", "ok")]
    loaded = ImportBatch.objects.get()
    assert (loaded.name, loaded.template_key) == ("Bar Pepe", "")
    assert [row.name for row in get("table.zone.list")(owner, get("table.zone.list").input(limit=10)).rows] == ["Patio"]


def test_a_copy_no_longer_attached_loads_nothing_and_the_model_hears_why(owner):
    # After the page reloads, the panel keeps an attachment by its name alone.
    reloaded = {"role": "user", "content": [{"type": "text", "text": f"[Attached: {NAME}]"}]}

    plan = turn(owner, [reloaded, asked(load_call())], [load_call()])

    assert plan["confirm"] is None
    told = json.loads(plan["append"][0]["content"])["error"]
    assert told["code"] == "base.assistant_attachment_missing"
    # Its receipt says why, as the person reads it.
    [receipt] = plan["executed"]
    assert (receipt["outcome"], receipt["code"]) == ("error", "base.assistant_attachment_missing")
    assert NAME in receipt["reason"]["es"]
    assert not ImportBatch.objects.exists()

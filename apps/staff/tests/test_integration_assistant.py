"""The assistant's card for a write of staff (FIX-HUB-STAFF-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Personal screens give it, never by the title pydantic makes up from
the field («Days», «Members»). The card is base's (``base.assistant.card``); the names are staff's: the titles of its
schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext
from live.operations import get, registry

from apps.staff.models import Member
from base import assistant
from base.tests.test_assistant import named_by_the_screen

from .conftest import ctx_for, make_role

SCREENS = json.loads((Path(apps.get_app_config("staff").path) / "frontend/locale/es.json").read_text())["staff"]

#: The data the Personal screens call by the code's very word, in Spanish too: the card says what the screen says.
SPELLED_ALIKE = {
    "color": SCREENS["members"]["form"]["color"],
    "bio": SCREENS["members"]["form"]["bio"],
}


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def staff_writes() -> list:
    return [op for op in registry.values() if op.app_label == "staff" and op.kind == "command" and assistant.is_tool(op)]


def test_no_datum_of_a_write_of_staff_reaches_a_spanish_card_by_its_technical_name():
    """Every write of staff the assistant may ask for, with all its data: each datum by a name of its own in Spanish
    (or the screen's word when Spanish spells it like the code), never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = staff_writes()
    assert len(writes) > 10  # positive control: the registry has staff's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            name, label = field["name"], field["label"]
            if name in SPELLED_ALIKE:
                assert label == SPELLED_ALIKE[name], (op.name, name)
            elif name not in screen and label == name.title().replace("_", " "):
                technical.setdefault(op.name, []).append(name)
    assert technical == {}


def test_the_card_names_a_schedules_week_as_its_form_does():
    week = [{"weekday": 0, "start_time": "09:00", "end_time": "17:00"}]
    for name in ("staff.schedule.create", "staff.schedule.update"):
        assert labels(assistant.card(get(name), {"days": week}, "es")) == [SCREENS["schedules"]["form"]["week"]]
        assert labels(assistant.card(get(name), {"days": week}, "en")) == ["Week"]


def test_the_card_names_the_people_of_a_batch_as_the_directory_does():
    batch = assistant.card(get("staff.member.bulk_create"), {"members": [{"first_name": "Ana", "last_name": "Gil"}]}, "es")
    assert labels(batch) == ["Miembros del personal"]
    english = assistant.card(get("staff.member.bulk_create"), {"members": [{"first_name": "Ana"}]}, "en")
    assert labels(english) == ["Staff members"]


def test_the_card_names_a_members_bio_and_colour_as_the_record_does():
    arguments = {"first_name": "Ana", "color": "#AABBCC", "bio": "Colorista."}
    record = SCREENS["members"]["form"]
    assert labels(assistant.card(get("staff.member.create"), arguments, "es")) == [
        record["firstName"],
        record["color"],
        record["bio"],
    ]


def test_the_card_paints_a_members_hourly_rate_as_money():
    """staff-business-currency: the hourly rate a write sends is an amount in the minor unit of the business's currency
    (the platform reads «in cents» so), and the card paints it as money in that currency with its decimals, never as
    the bare figure («1250» for 12,50 zł)."""
    for name in ("staff.member.create", "staff.member.update"):
        card = assistant.card(get(name), {"first_name": "Ana", "hourly_rate": 1250}, "es")
        rate = next(field for field in card["fields"] if field["name"] == "hourly_rate")
        assert (name, rate["kind"], rate["value"]) == (name, "money", 1250)


def test_the_card_names_the_hourly_rate_as_the_record_does_without_naming_cents():
    """staff-business-currency: the card paints the rate as money in the business's currency, whose minor unit is
    not always the cent (groszy in Poland, whole yen in Japan): its name is the record's, «Tarifa por hora», never
    «Tarifa por hora (céntimos)» beside «12,50 zł»."""
    for name in ("staff.member.create", "staff.member.update"):
        spanish = assistant.card(get(name), {"first_name": "Ana", "hourly_rate": 1250}, "es")
        assert [f["label"] for f in spanish["fields"] if f["name"] == "hourly_rate"] == [SCREENS["members"]["form"]["hourlyRate"]]
        english = assistant.card(get(name), {"first_name": "Ana", "hourly_rate": 1250}, "en")
        assert [f["label"] for f in english["fields"] if f["name"] == "hourly_rate"] == ["Hourly rate"]


# --- hub#538: a role the business does not have is told to the model before any card ------------------------------

ASKED_IN_SPANISH = {"role": "user", "content": "Da de alta al empleado «Luis QA» como cajero"}
LUIS = {"first_name": "Luis", "last_name": "QA", "role": "cajero"}


def call(name: str, arguments: dict, call_id: str = "c1") -> dict:
    return {"call_id": call_id, "name": assistant.tool_name(name), "arguments": json.dumps(arguments)}


def asked(*calls: dict) -> dict:
    """The model's message that asked for ``calls``, as the browser keeps it."""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": c["call_id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in calls
        ],
    }


def turn(*calls: dict, role: str = "hub_admin", decision: dict | None = None) -> dict:
    """A turn of the assistant of a person with ``role``, in Spanish, answering the model's ``calls``."""
    base_ctx = ctx_for(role)
    ctx = OperationContext(scope=base_ctx.scope, actor=base_ctx.actor, permissions=base_ctx.permissions, language="es")
    op = get("base.assistant.turn")
    data = {"messages": [ASKED_IN_SPANISH, asked(*calls)], "pending": list(calls), "decision": decision}
    return op(ctx, op.input.model_validate(data)).model_dump(mode="json")


def told(plan: dict) -> dict:
    """What the model hears of the only call of ``plan``."""
    return json.loads(plan["append"][0]["content"])



def test_a_new_member_tells_the_model_where_the_roles_are_and_checks_its_role_before_the_card():
    """The tool invites the model to read the business's roles first (``staff.role.list``), and the write names the
    read that checks its role before its card (``staff.role.resolve``, with the write's own permission)."""
    create = get("staff.member.create")
    assert "staff.role.list" in assistant.description(create)
    assert assistant.check_of(create) == "staff.role.resolve"
    resolve = get("staff.role.resolve")
    assert (resolve.kind, assistant.is_tool(resolve), resolve.permission) == ("query", False, create.permission)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [
        pytest.param({"role": "cajero"}, id="a-name-it-does-not-have"),
        pytest.param({"role": "Retired"}, id="a-retired-role"),
        pytest.param({"role_id": "0190a3b4-0000-7000-8000-000000000000"}, id="an-id-it-does-not-have"),
    ],
)
def test_a_new_member_with_a_role_the_business_does_not_have_gets_no_card_and_the_model_hears_why(role):
    """STAFF-F01 / BASE-F97: the role is checked before the card, not after the person's yes; the model hears which
    datum (``invalid_payload`` on ``role`` or ``role_id``) and nothing is created."""
    make_role("Retired", is_active=False)
    plan = turn(call("staff.member.create", {"first_name": "Luis", "last_name": "QA", **role}))
    assert plan["confirm"] is None
    assert [(row["name"], row["outcome"], row["code"]) for row in plan["executed"]] == [
        ("staff.member.create", "error", "invalid_payload")
    ]
    error = told(plan)["error"]
    assert (error["code"], set(error["fields"])) == ("invalid_payload", set(role))
    assert not Member.objects.exists()


@pytest.mark.django_db
def test_a_new_member_with_a_role_the_business_has_gets_its_card_and_the_yes_creates_it():
    """Positive control: the role exists (named in any case): the card comes, and the yes creates the member with it."""
    cashier = make_role("Cajero")
    luis = call("staff.member.create", LUIS)
    plan = turn(luis)
    assert (plan["confirm"]["operation"], plan["executed"]) == ("staff.member.create", [])
    done = turn(luis, decision={"call_id": "c1", "accepted": True, "typed": ""})
    assert [(row["outcome"], row["code"]) for row in done["executed"]] == [("ok", "")]
    assert list(Member.objects.values_list("first_name", "role_id")) == [("Luis", cashier.id)]

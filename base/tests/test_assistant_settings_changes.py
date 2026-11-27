"""Once the card of a change of settings is answered, the model hears how the data it sent stood and stand: after the
yes, what changed from what to what and what was already so; after a no, how they stay. It never has to guess what was
there before, and never tells as changed what was already so, nor the other way round (hub#2669, BASE-F97).

It holds for every write of settings the assistant can run: an edit of the one record of its kind that the business (or
the person) has, read back by a read that takes no data.
"""

import json
from functools import partial

import pytest
from live import assistant as shared
from live.operations import Operation, get, registry

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import owner_of_a
from base.tests.test_assistant_yes_for_its_card import turn_as, yes_to
from base.tests.test_services_assistant import call

__all__ = ["in_business_a"]

#: The writes the QA saw tell as «nothing changed» what changed, or the other way round.
SEEN = ("cash_register.settings.update", "reservation.settings.update", "schedule.settings.update")

#: The writes whose data take values a generic change cannot make up: the whole issuer, a PIN length, a region of the
#: business's country.
GIVEN = {
    "invoice.issuer.update": {
        "legal_name": "Bar QA Asistente SL",
        "tax_id": "B12345674",
        "address": "Calle Mayor 10",
        "intra_eu_operator": True,
    },
    "base.access.settings_update": {"pin_length": 6},
    "tax.settings.update": {"region_code": "ES-CN"},
}


def is_setting(op: Operation) -> bool:
    read = assistant.edits.state_read(op)
    return read is not None and not read.input.model_fields


def a_tool_write(op: Operation) -> bool:
    return op.kind == "command" and assistant.tools.is_tool(op)


SETTINGS = sorted(name for name, op in registry.items() if a_tool_write(op) and is_setting(op))


def named_as_a_setting(name: str) -> bool:
    return any(word in name for word in ("settings", "preferences", ".config."))


def answer(person, read: Operation) -> dict:
    return read(person, read.input()).model_dump(mode="json")


def heard(plan: dict) -> dict:
    """What the model hears of the call ``plan`` answered first."""
    return json.loads(plan["append"][0]["content"])


def no_to(person, plan: dict) -> dict:
    decision = {"call_id": plan["pending"][0]["call_id"], "accepted": False}
    return turn_as(person, *plan["pending"], decision=decision)


def a_change(op: Operation, before: dict) -> dict:
    """A call of ``op`` that changes one of its data: a yes or no turned over, another value of its list, the next whole
    number or another text, with each other datum ``op`` requires as it is now."""
    if op.name in GIVEN:
        return GIVEN[op.name]
    schema = shared.input_schema(op)
    props, defs = schema.get("properties", {}), schema.get("$defs", {})
    shaped = {name: _plain(props[name], defs) for name in props if name in before}
    for kind in ("boolean", "enum", "integer", "string"):
        for name, prop in shaped.items():
            value = _other(kind, prop, before[name])
            if value is not None:
                required = schema.get("required", [])
                return {**{datum: before[datum] for datum in required if datum in before}, name: value}
    raise AssertionError(f"{op.name}: no datum to change")


def _plain(prop: dict, defs: dict) -> dict:
    prop = shared.resolved(prop, defs)
    options = [shared.resolved(one, defs) for one in prop.get("anyOf", [])]
    return next((one for one in options if one.get("type") != "null"), prop)


def _other(kind: str, prop: dict, now: object) -> object:
    if kind == "boolean" and prop.get("type") == "boolean":
        return not now
    if kind == "enum" and "enum" in prop:
        return next((value for value in prop["enum"] if value != now), None)
    if kind == "integer" and prop.get("type") == "integer" and isinstance(now, int):
        up = now + 1
        return up if up <= prop.get("maximum", up) else now - 1
    if kind == "string" and prop.get("type") == "string" and "format" not in prop and "pattern" not in prop:
        return f"{now or ''} QA".strip()[: prop.get("maxLength", 100)]
    return None


@pytest.fixture
def owner(make_user):
    return owner_of_a(make_user, "es")


def test_the_writes_of_settings_are_found_and_every_one_named_as_a_setting_is_among_them():
    assert set(SEEN) <= set(SETTINGS)
    named = {
        name for name, op in registry.items() if a_tool_write(op) and op.input.model_fields and named_as_a_setting(name)
    }
    assert named - set(SETTINGS) == set()


#: Heard as they ran though a read of theirs answers their data unasked: the website's whole document, which would be
#: told three times over, and the mode of the device in use, read by another name.
HEARD_AS_THEY_RAN = {"base.device.mode_set", "website.site.save"}


def read_back_unasked(op: Operation) -> bool:
    """Whether a read of ``op``'s entity that takes no data answers every datum ``op`` sends, whatever both are called."""
    entity = op.name.rsplit(".", 1)[0]
    sent = {info.alias or name for name, info in op.input.model_fields.items()}
    answers = [
        set(getattr(read.output, "model_fields", ()))
        for name, read in registry.items()
        if read.kind == "query" and name.rsplit(".", 1)[0] == entity and not read.input.model_fields
    ]
    return bool(sent) and any(all(datum in told or f"{datum}_id" in told for datum in sent) for told in answers)


def test_a_write_of_settings_by_any_other_name_is_among_them_too():
    one_record = {name for name, op in registry.items() if a_tool_write(op) and read_back_unasked(op)}
    assert one_record - set(SETTINGS) == HEARD_AS_THEY_RAN


@pytest.mark.parametrize("write", SETTINGS)
def test_every_datum_of_a_write_of_settings_is_read_back(write):
    op = get(write)
    answered = set(assistant.edits.state_read(op).output.model_fields)
    sent = {info.alias or name for name, info in op.input.model_fields.items()}
    assert {datum for datum in sent if datum not in answered and f"{datum}_id" not in answered} == set()


@HUB_DB
@pytest.mark.parametrize("write", SETTINGS)
def test_the_model_hears_what_changed_what_was_already_so_and_how_it_stays(owner, write):
    op = get(write)
    assert write in assistant.tools.catalog(owner)
    read = assistant.edits.state_read(op)
    before = answer(owner, read)
    arguments = a_change(op, before)
    done = yes_to(turn_as(owner, call(write, arguments)), turn_of=partial(turn_as, owner))
    assert [row["outcome"] for row in done["executed"]] == ["ok"], done["executed"]
    after = answer(owner, read)
    changed = {name: {"from": before[name], "to": after[name]} for name in arguments if before[name] != after[name]}
    assert changed
    assert heard(done)["changed"] == changed
    assert sorted(heard(done)["already_so"]) == sorted(name for name in arguments if name not in changed)

    again = yes_to(turn_as(owner, call(write, arguments)), turn_of=partial(turn_as, owner))
    assert (heard(again)["changed"], sorted(heard(again)["already_so"])) == ({}, sorted(arguments))

    kept = answer(owner, read)
    declined = no_to(owner, turn_as(owner, call(write, arguments)))
    assert heard(declined)["as_it_stands"] == {name: after[name] for name in arguments}
    assert answer(owner, read) == kept


@HUB_DB
def test_the_till_set_up_at_once_tells_what_changed_and_what_was_already_so(owner):
    """«Configúrame la caja: que pida el fondo al abrir, que haya que contar el dinero al cerrar y que se cierre sola
    por la noche.», with the count already asked for: the rest changes."""
    write = "cash_register.settings.update"
    get(write)(
        owner,
        get(write).input(
            require_closing_balance=True, require_opening_balance=False, auto_close_enabled=False, auto_close_time="03:00"
        ),
    )
    arguments = {
        "require_opening_balance": True,
        "require_closing_balance": True,
        "auto_close_enabled": True,
        "auto_close_time": "04:00",
    }
    told = heard(yes_to(turn_as(owner, call(write, arguments)), turn_of=partial(turn_as, owner)))
    assert told["changed"] == {
        "require_opening_balance": {"from": False, "to": True},
        "auto_close_enabled": {"from": False, "to": True},
        "auto_close_time": {"from": "03:00", "to": "04:00"},
    }
    assert told["already_so"] == ["require_closing_balance"]
    assert told["require_closing_balance"] is True


@HUB_DB
def test_the_week_already_on_monday_is_told_so_after_the_yes_and_after_the_no(owner):
    """«Que la semana me empiece en lunes», with the week already starting on Monday."""
    write = "schedule.settings.update"
    get(write)(owner, get(write).input(week_starts_on=1))
    whole = answer(owner, get("schedule.settings.get"))
    told = heard(yes_to(turn_as(owner, call(write, {"week_starts_on": 1})), turn_of=partial(turn_as, owner)))
    assert (told["changed"], told["already_so"]) == ({}, ["week_starts_on"])
    assert {key: told[key] for key in whole} == whole
    declined = heard(no_to(owner, turn_as(owner, call(write, {"week_starts_on": 7}))))
    assert declined["as_it_stands"] == {"week_starts_on": 1}
    assert declined["error"]["code"] == "base.assistant_not_confirmed"


@HUB_DB
def test_an_edit_of_a_record_by_its_id_tells_what_changed_too(owner):
    create = get("demo.item.create")
    item = create(owner, create.input(name="Mesa 4")).model_dump(mode="json")
    arguments = {"id": item["id"], "note": "Junto a la ventana", "name": "Mesa 4"}
    told = heard(yes_to(turn_as(owner, call("demo.item.update", arguments)), turn_of=partial(turn_as, owner)))
    assert (told["changed"], told["already_so"]) == ({"note": {"from": "", "to": "Junto a la ventana"}}, ["name"])


@HUB_DB
def test_a_write_that_is_not_an_edit_is_heard_as_it_ran(owner):
    done = yes_to(turn_as(owner, call("demo.item.create", {"name": "Mesa 5"})), turn_of=partial(turn_as, owner))
    assert {"changed", "already_so", "as_it_stands"} & set(heard(done)) == set()


@HUB_DB
def test_a_datum_that_names_another_record_is_told_by_the_name_its_answer_gives_it(owner):
    """The receipts' printer, sent by its name, is ``receipt_printer_id`` in the answer the model reads."""
    create = get("printing.printer.create")
    till = create(owner, create.input(name="Caja", kind="network", address="192.168.1.100", usage="receipt"))
    arguments = {"receipt_printer": "Caja"}
    told = heard(yes_to(turn_as(owner, call("printing.settings.update", arguments)), turn_of=partial(turn_as, owner)))
    assert told["changed"] == {"receipt_printer_id": {"from": None, "to": str(till.id)}}

"""FIX-HUB-SCHEDULE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#675): the card of a write of Schedules says which special
day or temporary change it acts on by its name, read as whoever asks, never by its id, and leaves it out when that
person may not read it or it is not there. A special day goes by its name and a temporary change by its reason, as the
screens' own «Delete» dialog says them («It will delete “Christmas”»).
"""

import dataclasses

import pytest
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.operations import INTERNAL, get

from apps.schedule.tests.conftest import A, ctx_for, make_override, make_special_day
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

#: The writes on a special day and on a temporary change the model names by its id.
ON_A_SPECIAL_DAY = ["schedule.special_day.delete", "schedule.special_day.update"]
ON_AN_OVERRIDE = ["schedule.override.delete", "schedule.override.update"]


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for())
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def without(permission: str, scope: Scope = A) -> OperationContext:
    """An admin of ``scope`` without ``permission``: a combination no role has."""
    ctx = ctx_for(scope=scope)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {permission})


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


# ── A special day, by its name; a temporary change, by its reason ─────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Special day"), ("es", "Día especial")])
@pytest.mark.parametrize("write", ON_A_SPECIAL_DAY)
def test_a_write_on_a_special_day_says_it_by_its_name(write, language, title):
    """The case the issue names: deleting or changing a special day says which one, «Día especial: Navidad»."""
    christmas = make_special_day("2026-12-25", "Navidad")
    field = fields_of(write, {"id": str(christmas.id)}, language)["id"]
    assert (field["value"], field["label"]) == ("Navidad", title)


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Temporary change"), ("es", "Cambio temporal")])
@pytest.mark.parametrize("write", ON_AN_OVERRIDE)
def test_a_write_on_a_temporary_change_says_it_by_its_reason(write, language, title):
    """«schedule.override.delete:id», the datum the issue cites: «Cambio temporal: Horario de verano»."""
    summer = make_override("2026-07-01", "2026-08-31", "Horario de verano", ("09:00", "15:00"))
    field = fields_of(write, {"id": str(summer.id)}, language)["id"]
    assert (field["value"], field["label"]) == ("Horario de verano", title)


@pytest.mark.django_db
def test_a_change_keeps_saying_the_record_beside_what_it_changes():
    """The name is the record's as it is now, before the write runs: a rename says the old name under «Special day»
    and the new one under its own datum."""
    christmas = make_special_day("2026-12-25", "Navidad")
    said = shown("schedule.special_day.update", {"id": str(christmas.id), "name": "Nochebuena"})
    assert (said["id"], said["name"]) == ("Navidad", "Nochebuena")


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("write", ON_A_SPECIAL_DAY + ON_AN_OVERRIDE)
def test_what_the_person_may_not_read_is_left_out_never_said_by_its_id(write):
    """Whoever may not see the opening hours (``schedule.view``) is told no special day nor temporary change."""
    record = make_special_day() if ".special_day." in write else make_override()
    arguments = {"id": str(record.id)}
    assert "id" in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("schedule.view"))
    assert "id" not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize("write", ON_A_SPECIAL_DAY + ON_AN_OVERRIDE)
def test_what_does_not_exist_is_left_out(write):
    said = shown(write, {"id": A_MISSING_ID})
    assert "id" not in said
    assert no_id(said)


@pytest.mark.django_db
def test_a_record_deleted_meanwhile_is_left_out():
    christmas = make_special_day("2026-12-25", "Navidad")
    arguments = {"id": str(christmas.id)}
    assert shown("schedule.special_day.delete", arguments) == {"id": "Navidad"}  # positive control
    christmas.delete()
    assert shown("schedule.special_day.delete", arguments) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    summer = make_override(reason="Horario de verano")
    card = assistant.card(get("schedule.override.update"), {"id": str(summer.id), "reason": "Verano"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"reason": "Verano"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        records = [
            ("schedule.special_day.delete", make_special_day("2026-12-25", "Navidad")),
            ("schedule.override.delete", make_override(reason="Horario de verano")),
        ]
        for write, record in records:  # positive control
            assert "id" in shown(write, {"id": str(record.id)}, ctx=in_a), write
    with use_hub(hub_b):
        for write, record in records:
            assert "id" not in shown(write, {"id": str(record.id)}, ctx=in_b), write


# ── The reads that name them ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("read", ["schedule.special_day.get", "schedule.override.get"])
def test_the_reads_that_name_them_are_no_tool_and_no_door_of_the_api(read):
    """Only the card reads them; the model finds special days and temporary changes in their lists."""
    op = get(read)
    assert (op.kind, op.permission, op.ai, op.expose_api) == ("query", "schedule.view", INTERNAL, False)


@pytest.mark.django_db
def test_the_reads_answer_the_record_as_its_list_does_to_whoever_sees_the_hours():
    christmas = make_special_day("2026-12-25", "Navidad")
    summer = make_override("2026-07-01", "2026-08-31", "Horario de verano", ("09:00", "15:00"))
    employee = ctx_for("hub_employee")
    special = get("schedule.special_day.get")
    change = get("schedule.override.get")
    said = special(employee, special.input.model_validate({"id": str(christmas.id)}))
    assert (said.id, said.name, str(said.date), said.is_closed) == (christmas.id, "Navidad", "2026-12-25", True)
    said = change(employee, change.input.model_validate({"id": str(summer.id)}))
    assert (said.id, said.reason, said.is_closed, len(said.intervals)) == (summer.id, "Horario de verano", False, 1)


@pytest.mark.django_db
@pytest.mark.parametrize("read", ["schedule.special_day.get", "schedule.override.get"])
def test_a_read_of_what_is_not_there_is_a_404_and_without_the_permission_a_403(read):
    op = get(read)
    with pytest.raises(NotFound):
        op(ctx_for(), op.input.model_validate({"id": A_MISSING_ID}))
    record = make_special_day() if ".special_day." in read else make_override()
    with pytest.raises(PermissionDenied):
        op(without("schedule.view"), op.input.model_validate({"id": str(record.id)}))

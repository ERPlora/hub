"""FIX-HUB-APPOINTMENT-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#635): the card of a write of Appointments says which
record it acts on by its name, read as whoever asks, never by an id, and leaves it out when that person may not read it
or it is not there. A professional goes by their name, an appointment by its customer, day, hour and professional (as
the Agenda tells one from another), a repeating appointment as the series list titles one («Lucía Pérez · Every week ·
Monday · 10:00») and a blocked period by its title, its day and its professional, each under the word its list calls
one. Before, every one of them was left out (hub#416) and a bulk delete said «Ids» with nothing in it.
"""

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import get, registry

from apps.schedule.queries import day_label
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID, list_field

from .conftest import A, MONDAY, at, ctx_for, make_appointment, make_block, make_salon, make_series, run

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

SCREENS = Path(apps.get_app_config("appointment").path) / "frontend/locale"

#: The writes that name the professional who takes the appointments, the series or the block.
NAME_A_PROFESSIONAL = [
    "appointment.appointment.bulk_create",
    "appointment.appointment.create",
    "appointment.appointment.reschedule",
    "appointment.appointment.update",
    "appointment.blocked_time.create",
    "appointment.recurring.create",
    "appointment.recurring.update",
]
#: The writes on one appointment named by its id (titled «Appointment» since hub#797).
ON_AN_APPOINTMENT = [
    f"appointment.appointment.{action}"
    for action in ("cancel", "charge", "complete", "confirm", "delete", "mark_no_show", "reschedule", "start", "update")
]
#: The writes on one repeating appointment named by its id.
ON_A_SERIES = [
    "appointment.recurring.activate",
    "appointment.recurring.deactivate",
    "appointment.recurring.delete",
    "appointment.recurring.materialize",
    "appointment.recurring.update",
]

#: The word the card calls a blocked period by, in each language: no list of the Hub calls one.
BLOCKED_PERIOD = {"en": "Blocked period", "es": "Bloqueo"}


def screens(language: str) -> dict:
    return json.loads((SCREENS / f"{language}.json").read_text())["appointment"]


def word(language: str, *path: str) -> str:
    """What a list of Appointments calls one or many (``series.entity.one``, ``list.entity.many``), as a title."""
    node = screens(language)
    for key in path:
        node = node[key]
    return node[:1].upper() + node[1:]


def as_admin(language: str = "en", scope: Scope = A) -> OperationContext:
    return ctx_for(scope=scope, language=language)


def without(permissions: set[str], language: str = "en") -> OperationContext:
    """An admin without ``permissions``: a combination no role has."""
    ctx = as_admin(language)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - permissions)


def card_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return assistant.card(get(write), arguments, language, ctx or as_admin(language))


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {field["name"]: field for field in card_of(write, arguments, language, ctx)["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def no_id(said) -> bool:
    return not AN_ID.search(json.dumps(said, ensure_ascii=False, default=str))


def appointment_writes() -> list:
    return [
        op
        for _, op in sorted(registry.items())
        if op.app_label == "appointment" and op.kind == "command" and assistant.is_tool(op)
    ]


@dataclasses.dataclass
class Diary:
    """Two appointments (Ana's and Bea's), a weekly series of Lucía with Ana, and two blocks: Ana's training on Monday
    afternoon and the whole business's holiday the day after."""

    salon: object
    ana_at_ten: object
    bea_at_eleven: object
    series: object
    training: object
    holiday: object


def make_diary(salon) -> Diary:
    tuesday = MONDAY + dt.timedelta(days=1)
    return Diary(
        salon=salon,
        ana_at_ten=make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00")),
        bea_at_eleven=make_appointment(salon.lucia, salon.bea, [salon.colour], at(MONDAY, "11:00")),
        series=make_series(salon),
        training=make_block(at(MONDAY, "14:00"), at(MONDAY, "15:30"), member=salon.ana, title="Training"),
        holiday=make_block(
            at(tuesday, "00:00"), at(tuesday + dt.timedelta(days=1), "00:00"), title="Local holiday", all_day=True
        ),
    )


def appointment_said(language: str, hour: str, professional: str) -> str:
    return f"Lucía Pérez · {day_label(MONDAY, language)} · {hour} · {professional}"


# ── A professional, by their name ─────────────────────────────────────────────────────────────────────────────────────


def professional_of(write: str, diary: Diary) -> dict:
    """``write`` with Bea as its professional, on the record it changes when it changes one."""
    sent = {"staff_id": str(diary.salon.bea.id)}
    if write in ("appointment.appointment.reschedule", "appointment.appointment.update"):
        return {"id": str(diary.ana_at_ten.id), **sent}
    if write == "appointment.recurring.update":
        return {"id": str(diary.series.id), **sent}
    return sent


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("write", NAME_A_PROFESSIONAL)
def test_every_write_that_names_a_professional_says_them_by_their_name(salon, write, language):
    """The case the issue names, «appointment.appointment.bulk_create:staff_id»: the professional by the name the Staff
    list gives them, under the word the Agenda's column calls one («Professional»)."""
    diary = make_diary(salon)
    field = fields_of(write, professional_of(write, diary), language).get("staff_id", {})
    title = {"en": "Professional", "es": "Profesional"}[language]
    assert (field.get("value"), field.get("label")) == ("Bea Ruiz", title)


# ── An appointment of a bulk delete, a series and a block, by their names ─────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_bulk_delete_says_each_appointment_as_the_agenda_tells_it_and_how_many(salon, language):
    """Whoever confirms deleting several appointments sees which ones they are, never «Ids» with nothing in it."""
    diary = make_diary(salon)
    card = card_of(
        "appointment.appointment.bulk_delete",
        {"ids": [str(diary.bea_at_eleven.id), str(diary.ana_at_ten.id)]},
        language,
    )
    field = list_field(card, "ids")
    assert field["value"] == [
        appointment_said(language, "11:00", "Bea Ruiz"),
        appointment_said(language, "10:00", "Ana López"),
    ]
    assert field["label"] == word(language, "list", "entity", "many")
    assert card["count"] == 2
    assert no_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("write", ON_A_SERIES)
def test_a_write_on_a_series_says_it_as_the_series_list_titles_one(salon, write, language):
    """A series by its customer and its repetition, as each card of the series list is titled, under the word that list
    calls one («Repeating appointment»)."""
    diary = make_diary(salon)
    field = fields_of(write, {"id": str(diary.series.id)}, language).get("id", {})
    said = {"en": "Lucía Pérez · Every week · Monday · 10:00", "es": "Lucía Pérez · Cada semana · Lunes · 10:00"}
    assert (field.get("value"), field.get("label")) == (said[language], word(language, "series", "entity", "one"))


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("frequency", "said"),
    [
        ("daily", "Lucía Pérez · Every day · 10:00"),
        ("biweekly", "Lucía Pérez · Every two weeks · Monday · 10:00"),
        ("monthly", "Lucía Pérez · Every month · 10:00"),
    ],
)
def test_a_series_says_its_weekday_only_when_it_repeats_by_the_week(salon, frequency, said):
    """As the series list: a weekday only for a weekly or biweekly series."""
    series = make_series(salon, frequency=frequency, day_of_week=0 if "week" in frequency else None)
    assert shown("appointment.recurring.deactivate", {"id": str(series.id)}) == {"id": said}


@pytest.mark.django_db
def test_a_series_whose_customer_was_erased_and_whose_professional_left_still_says_its_repetition(salon):
    series = make_series(salon)
    series.customer_name = ""
    series.save(update_fields=["customer_name"])
    assert shown("appointment.recurring.delete", {"id": str(series.id)}) == {"id": "Every week · Monday · 10:00"}


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_removing_a_block_says_its_title_its_day_its_hour_and_whose_it_is(salon, language):
    """A blocked period by its title, as the Agenda paints it, its day and hour and its professional; a whole day says no
    hour and a block of the whole business no professional."""
    diary = make_diary(salon)
    training = fields_of("appointment.blocked_time.delete", {"id": str(diary.training.id)}, language)["id"]
    assert (training["value"], training["label"]) == (
        f"Training · {day_label(MONDAY, language)} · 14:00 · Ana López",
        BLOCKED_PERIOD[language],
    )
    holiday = shown("appointment.blocked_time.delete", {"id": str(diary.holiday.id)}, language)
    assert holiday == {"id": f"Local holiday · {day_label(MONDAY + dt.timedelta(days=1), language)}"}


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names(salon):
    """Each id names its own record, never another of the list (the first, the last, the newest)."""
    diary = make_diary(salon)
    other_series = make_series(salon, staff=salon.bea, frequency="daily", day_of_week=None)
    series = [shown("appointment.recurring.activate", {"id": str(s.id)})["id"] for s in (other_series, diary.series)]
    assert series == ["Lucía Pérez · Every day · 10:00", "Lucía Pérez · Every week · Monday · 10:00"]
    blocks = [shown("appointment.blocked_time.delete", {"id": str(b.id)})["id"] for b in (diary.holiday, diary.training)]
    assert [block.split(" · ")[0] for block in blocks] == ["Local holiday", "Training"]
    professionals = [
        shown("appointment.blocked_time.create", {"title": "Off", "staff_id": str(m.id)}).get("staff_id")
        for m in (salon.bea, salon.ana)
    ]
    assert professionals == ["Bea Ruiz", "Ana López"]


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_professional_the_person_may_not_read_is_left_out_never_said_by_their_id(salon):
    """The professional is read by Staff's own read (``staff.view``): without it, the card names nobody."""
    diary = make_diary(salon)
    arguments = professional_of("appointment.appointment.bulk_create", diary)
    assert shown("appointment.appointment.bulk_create", arguments)["staff_id"] == "Bea Ruiz"  # positive control
    said = shown("appointment.appointment.bulk_create", arguments, ctx=without({"staff.view"}))
    assert "staff_id" not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize("write", ON_A_SERIES)
def test_a_series_the_person_may_not_read_is_left_out(salon, write):
    diary = make_diary(salon)
    arguments = {"id": str(diary.series.id)}
    assert "id" in shown(write, arguments)  # positive control
    blind = without({"appointment.view_appointment", "appointment.view_own_appointment"})
    said = shown(write, arguments, ctx=blind)
    assert "id" not in said
    assert no_id(said)


@pytest.mark.django_db
def test_an_employee_reads_no_series_of_somebody_else(salon):
    """An employee sees only their own diary (``visible``): somebody else's series is not theirs to read."""
    diary = make_diary(salon)
    employee = ctx_for(role="hub_employee")
    assert shown("appointment.recurring.deactivate", {"id": str(diary.series.id)}, ctx=employee) == {}


@pytest.mark.django_db
def test_a_block_the_person_may_not_read_is_left_out(salon):
    diary = make_diary(salon)
    arguments = {"id": str(diary.training.id)}
    assert "id" in shown("appointment.blocked_time.delete", arguments)  # positive control
    said = shown("appointment.blocked_time.delete", arguments, ctx=without({"appointment.view_schedule"}))
    assert said == {}


@pytest.mark.django_db
def test_appointments_the_person_may_not_read_are_counted_never_named_nor_said_by_their_id(salon):
    """A list says how many it carries even when none can be named for this person (live.assistant ``said``)."""
    diary = make_diary(salon)
    arguments = {"ids": [str(diary.ana_at_ten.id), str(diary.bea_at_eleven.id)]}
    blind = without({"appointment.view_appointment", "appointment.view_own_appointment"})
    card = card_of("appointment.appointment.bulk_delete", arguments, ctx=blind)
    assert list_field(card, "ids")["value"] == [None, None]
    assert no_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize("write", ["appointment.blocked_time.delete", *ON_A_SERIES])
def test_a_record_that_does_not_exist_is_left_out(salon, write):
    make_diary(salon)
    assert shown(write, {"id": A_MISSING_ID}) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record(salon):
    """An automation's card (no person at hand) names no professional, series nor block: nothing is read."""
    diary = make_diary(salon)
    arguments = {"id": str(diary.training.id)}
    assert "id" in shown("appointment.blocked_time.delete", arguments)  # positive control
    for write, sent in (
        ("appointment.blocked_time.delete", arguments),
        ("appointment.recurring.delete", {"id": str(diary.series.id)}),
        ("appointment.blocked_time.create", {"title": "Off", "staff_id": str(salon.ana.id)}),
    ):
        card = assistant.card(get(write), sent, "en")
        assert no_id(card), write
        assert {"id", "staff_id"}.isdisjoint(field["name"] for field in card["fields"]), write


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = as_admin(scope=Scope("host", hub_a.slug)), as_admin(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        diary = make_diary(make_salon())
        on_the_series, on_the_block = {"id": str(diary.series.id)}, {"id": str(diary.training.id)}
        on_the_member = {"title": "Off", "staff_id": str(diary.salon.ana.id)}
        assert shown("appointment.recurring.delete", on_the_series, ctx=in_a)["id"]  # positive control
        assert shown("appointment.blocked_time.delete", on_the_block, ctx=in_a)["id"]
        assert shown("appointment.blocked_time.create", on_the_member, ctx=in_a)["staff_id"] == "Ana López"
    with use_hub(hub_b):
        assert shown("appointment.recurring.delete", on_the_series, ctx=in_b) == {}
        assert shown("appointment.blocked_time.delete", on_the_block, ctx=in_b) == {}
        assert "staff_id" not in shown("appointment.blocked_time.create", on_the_member, ctx=in_b)


# ── The reads that name a series and a block ──────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_series_is_named_in_the_language_of_whoever_reads_it_whatever_the_one_active(salon):
    """The model and the API read a series too (``appointment.recurring.get``): its name is in the caller's language,
    not in the one the server happens to have active (English here)."""
    diary = make_diary(salon)
    spanish = run("appointment.recurring.get", {"id": str(diary.series.id)}, language="es")
    assert spanish.label == "Lucía Pérez · Cada semana · Lunes · 10:00"


@pytest.mark.django_db
def test_a_block_is_named_in_the_language_of_whoever_reads_it_whatever_the_one_active(salon):
    diary = make_diary(salon)
    spanish = run("appointment.blocked_time.get", {"id": str(diary.holiday.id)}, language="es")
    assert spanish.label == f"Local holiday · {day_label(MONDAY + dt.timedelta(days=1), 'es')}"


def test_the_read_that_names_a_block_is_no_tool_nor_route():
    """Only the card reads a block by its id: the model reads them by their list, and no screen asks for one."""
    read = get("appointment.blocked_time.get")
    assert (read.kind, read.expose_api, assistant.is_tool(read)) == ("query", False, False)
    assert read.permission == get("appointment.blocked_time.list").permission


# ── Titles: every record by a word of its own ─────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_every_record_a_write_names_is_titled_with_the_screens_word_in_each_language(salon, language):
    """Every datum of a write of Appointments that names a record, sent with a real one, is called as its list calls one
    — in each language, never «Record», «Id» nor «Staff Id» — and is said by its name, never by its id."""
    diary = make_diary(salon)
    sent = {
        "appointment.appointment": str(diary.ana_at_ten.id),
        "appointment.recurring": str(diary.series.id),
        "appointment.blocked_time": str(diary.training.id),
    }
    titles = {}
    for op in appointment_writes():
        props = op.input.model_json_schema().get("properties", {})
        record = sent.get(op.name.rsplit(".", 1)[0])
        for datum, value in (("id", record), ("ids", [str(diary.ana_at_ten.id)]), ("staff_id", str(salon.bea.id))):
            if datum in props:
                field = fields_of(op.name, {datum: value}, language).get(datum, {})
                titles[f"{op.name}:{datum}"] = (field.get("label"), bool(field.get("value")), no_id(field.get("value")))
    professional = {"en": "Professional", "es": "Profesional"}[language]
    assert titles == {
        **{f"{write}:id": (word(language, "list", "entity", "one"), True, True) for write in ON_AN_APPOINTMENT},
        **{f"{write}:id": (word(language, "series", "entity", "one"), True, True) for write in ON_A_SERIES},
        "appointment.blocked_time.delete:id": (BLOCKED_PERIOD[language], True, True),
        "appointment.appointment.bulk_delete:ids": (word(language, "list", "entity", "many"), True, True),
        **{f"{write}:staff_id": (professional, True, True) for write in NAME_A_PROFESSIONAL},
    }

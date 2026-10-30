"""The assistant's card names every datum a write of Automations sends (FIX-HUB-FLOW-ASSISTANT-CARD-FIELDS-IN-ENGLISH;
base's half is hub#258): in Spanish, by the name the Automations screens give it, never by the title pydantic makes up
from the field («Actor», «Draft Id», «Event Id»). The card is base's (``base.assistant.card``); the names are flow's: the
titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog. Where the editor
already has words for the datum (``flow.fields.<name>``, ``frontend/locale/{en,es}.json``), the card says the same.

And which writes are tools at all: what only the platform runs (the outbox relay, the worker, the scheduled tasks,
under ``flow.system``) is «System only», and a secret's value is never asked for in a chat («Not an assistant tool»:
the person types it in the automation's step) — not even who may do everything is offered them."""

import datetime as dt
import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import Scope
from live.operations import get, registry

from apps.flow.queries import SYSTEM
from apps.flow.tests.conftest import ctx_for, make_draft, make_flow, make_run
from base import assistant
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID

APP = Path(apps.get_app_config("flow").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["flow"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["flow"]

#: The writes of Automations the assistant calls, by name.
TOOLS = sorted(
    name for name, op in registry.items() if op.app_label == "flow" and op.kind == "command" and assistant.is_tool(op)
)
#: The writes of Automations only the platform runs: the outbox relay, the worker and the scheduled tasks.
PLATFORM = sorted(
    name for name, op in registry.items() if op.app_label == "flow" and op.kind == "command" and op.permission == SYSTEM
)
#: What the assistant is never offered: the platform's writes and saving a secret, whose value is typed on the screen.
NEVER_TOOLS = [*PLATFORM, "flow.secret.set"]


def test_what_only_the_platform_runs_is_system_only():
    """A write under ``flow.system`` reacts to the outbox, makes a run's call or runs a scheduled task: in the hands of
    the assistant it could start automations or make up how a call ended. «System only» keeps it out of every
    catalogue, the next one too."""
    assert {"flow.run.react", "flow.run.record_call", "flow.schedule.fire_due"} <= set(PLATFORM)  # positive control
    assert [name for name in PLATFORM if not assistant.description(get(name)).startswith("System only")] == []


def test_a_secrets_value_is_never_asked_for_in_a_chat():
    """A secret said in a chat has already reached the model and the history: the person types it in the automation's
    step, on the screen (as ChatGPT's actions, Zapier or Make ask for credentials: in their form, never in the chat)."""
    secret = get("flow.secret.set")
    assert assistant.description(secret).startswith("Not an assistant tool")
    assert not assistant.is_tool(secret)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("permissions", [None, {"*"}], ids=["owner", "superuser"])
def test_not_even_who_may_do_everything_is_offered_them(permissions):
    tools = assistant.catalog(ctx_for("hub_owner", permissions=permissions))
    assert {"flow.flow.create", "flow.question.answer"} <= set(tools)  # positive control: flow's tools are offered
    assert sorted(set(NEVER_TOOLS) & set(tools)) == []
    assert [name for name in NEVER_TOOLS if assistant.is_tool(get(name))] == []


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_flow(op, name: str, title: str | None) -> bool:
    """Whether flow itself names the datum ``name`` of ``op``: by its schema's own title, by the ``verbose_name`` of one
    of its models, or by its own catalog. A title pydantic made up that another app's catalog happens to translate is
    not a name of Automations: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("flow", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_flow_reaches_a_spanish_card_by_its_technical_name():
    """Every write of flow the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up. By where the name comes from, not by the word."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 15  # positive control: the registry has flow's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_flow(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_who_caused_an_event_as_the_editor():
    """An event an automation reacts to: who caused it is «Quién lo hizo», as the editor's «Which data?» says it."""
    react = get("flow.run.react")
    assert labels(assistant.card(react, {"actor": "x"}, "es")) == [SCREENS["fields"]["actor"]] == ["Quién lo hizo"]
    assert labels(assistant.card(react, {"actor": "x"}, "en")) == [SCREENS_EN["fields"]["actor"]]


def test_the_card_names_the_event_an_automation_reacts_to():
    arguments = {"event_id": "x", "event": "sale.sale.completed", "payload": {"total": 1}}
    react = get("flow.run.react")
    assert labels(assistant.card(react, arguments, "es")) == [
        "Referencia de lo que pasó",
        "Qué pasó",
        SCREENS["picker"]["input"],
    ]
    assert labels(assistant.card(react, arguments, "en")) == [
        "Reference of what happened",
        "What happened",
        SCREENS_EN["picker"]["input"],
    ]


def test_the_card_names_how_it_starts_and_the_draft_as_the_list():
    for name in ("flow.flow.create", "flow.flow.update"):
        arguments = {"trigger": {"kind": "manual"}}
        assert labels(assistant.card(get(name), arguments, "es")) == [SCREENS["list"]["filterTrigger"]]
        assert labels(assistant.card(get(name), arguments, "en")) == [SCREENS_EN["list"]["filterTrigger"]]

@pytest.mark.django_db
def test_the_card_names_the_draft_an_automation_is_created_from_as_the_list():
    """Its label as the list's badge, and the draft by its name. (Since hub#416 a card leaves out a record it cannot
    name — an automation's card reads nothing —, so the card is asked as the person who confirms, about a draft that
    exists.)"""
    draft = make_draft()
    create = get("flow.flow.create")
    for language, screens in (("es", SCREENS), ("en", SCREENS_EN)):
        card = assistant.card(create, {"draft_id": str(draft.id)}, language, ctx=ctx_for(language=language))
        assert said(card) == [(screens["drafts"]["badge"], "Call who did not come")], language


def test_the_card_names_what_an_automation_may_do_as_its_permissions_tab():
    grant = get("flow.flow.grant")
    arguments = {"operations": ["sale.sale.void"]}
    assert labels(assistant.card(grant, arguments, "es")) == [SCREENS["editor"]["tabs"]["permissions"]]
    assert labels(assistant.card(grant, arguments, "en")) == [SCREENS_EN["editor"]["tabs"]["permissions"]]


def test_the_card_names_the_answer_to_a_question():
    """«Waiting for your answer» asks yes or no: the card says the person's answer, «Respuesta: Sí»."""
    answer = get("flow.question.answer")
    assert labels(assistant.card(answer, {"approve": True}, "es")) == ["Respuesta"]
    assert labels(assistant.card(answer, {"approve": True}, "en")) == ["Answer"]


def test_the_card_names_a_secrets_value_as_the_secrets_screen():
    secret = get("flow.secret.set")
    assert labels(assistant.card(secret, {"value": "x"}, "es")) == [SCREENS["secrets"]["value"]]
    assert labels(assistant.card(secret, {"value": "x"}, "en")) == [SCREENS_EN["secrets"]["value"]]


def test_the_card_names_how_a_call_ended_with_the_words_of_its_step():
    """A call of a run leaves ``status``, ``body`` and ``truncated`` to the next steps: the card names them as the
    editor does, and what went wrong as the history's technical text."""
    record = get("flow.run.record_call")
    arguments = {"kind": "ok", "body": "x", "truncated": False, "detail": "x"}
    assert labels(assistant.card(record, arguments, "es")) == [
        "Cómo terminó",
        SCREENS["fields"]["body"],
        SCREENS["fields"]["truncated"],
        "Texto técnico",
    ]
    assert labels(assistant.card(record, arguments, "en")) == [
        "How it ended",
        SCREENS_EN["fields"]["body"],
        SCREENS_EN["fields"]["truncated"],
        "Technical text",
    ]


@pytest.mark.django_db
def test_flow_f17_the_assistant_may_leave_a_draft_automation_and_only_a_draft():
    """FLOW-F17: «create a flow that creates a task when a sale over 100 € is completed», said in the Hub's chat, is
    ``flow.draft.propose`` run as the person: a draft waits in Automations; nothing is created, granted or run."""
    from apps.flow.models import Draft, Flow

    owner = ctx_for("hub_owner")
    propose = assistant.catalog(owner).get("flow.draft.propose")
    assert propose is not None and propose.kind == "command"
    definition = {
        "trigger": {"kind": "event", "event": "sale.sale.completed", "filter": {"input.total": {"gt": 10000}}},
        "steps": [{"id": "s1", "kind": "command", "operation": "task.task.create", "params": {"title": "Big sale"}}],
    }
    outcome = assistant.run_tool(owner, propose, json.dumps({"name": "Big sales", "definition": definition, "notes": []}))
    assert outcome.outcome == "ok", outcome.content
    draft = Draft.objects.get()
    assert (draft.name, draft.status) == ("Big sales", Draft.Status.PENDING)
    assert Flow.objects.count() == 0
    assert "flow.draft.propose" not in assistant.catalog(ctx_for("hub_employee"))


# ── Each record a write names by its id, as its screen names it (FIX-HUB-FLOW-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS) ──
# Since hub#416 the card leaves out every id its schema does not mark with the read that names its record (before, the
# UUID showed). Automations marks each one with a read by id of its own, run as the person who confirms: an automation by
# its name, a draft by its name, a run by its automation and when it started, a question by what it asks. A record they
# may not read, or of another business, is left out — never by its id.

#: Thursday 15 October 2026 at 21:00 in Madrid, as each language writes a day and a time on the card (base's CLDR words).
STARTED = dt.datetime(2026, 10, 15, 19, 0, tzinfo=dt.UTC)
WHEN = {"es": "15 oct 2026, 21:00", "en": "Oct 15, 2026, 9:00\u202fPM"}
#: The writes of an automation the assistant names by its id (FLOW-F01 to F05, F09, F14).
AUTOMATION_WRITES = [
    "flow.flow.update",
    "flow.flow.set_enabled",
    "flow.flow.duplicate",
    "flow.flow.delete",
    "flow.flow.grant",
    "flow.flow.run",
]


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def said(card: dict) -> list[tuple[str, object]]:
    return [(field["label"], field["value"]) for field in card["fields"]]


def by_an_id(card: dict) -> bool:
    return bool(AN_ID.search(json.dumps(card, ensure_ascii=False)))


def card_for(name: str, arguments: dict, language: str, ctx=None) -> dict:
    return assistant.card(get(name), arguments, language, ctx=ctx or ctx_for(language=language))


# FLOW-F03 «Encender o pausar», asked to the assistant: the card says which automation, by its name.
@pytest.mark.django_db
@pytest.mark.parametrize(("language", "on"), [("es", "Encendida"), ("en", "On")])
def test_turning_an_automation_on_names_it_never_by_its_id(language, on):
    """A yes or no goes as it is: the card paints it in the person's words."""
    welcome = make_flow("Welcome", enabled=False)
    card = card_for("flow.flow.set_enabled", {"id": str(welcome.id), "enabled": True}, language)
    assert values(card) == {"id": "Welcome", "enabled": True}
    assert (on, True) in said(card)
    assert not by_an_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_every_write_of_an_automation_names_it_by_its_name(language):
    welcome = make_flow("Welcome")
    for name in AUTOMATION_WRITES:
        card = card_for(name, {"id": str(welcome.id)}, language)
        assert values(card)["id"] == "Welcome", name
        assert not by_an_id(card), name


# FLOW-F23/F24: discarding a draft the assistant proposed, or creating the automation from it.
@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_discarding_a_draft_or_creating_an_automation_from_it_names_the_draft(language):
    draft = make_draft("Call who did not come")
    assert values(card_for("flow.draft.dismiss", {"id": str(draft.id)}, language)) == {"id": "Call who did not come"}
    card = card_for("flow.flow.create", {"name": "Call them", "draft_id": str(draft.id)}, language)
    assert values(card)["draft_id"] == "Call who did not come"
    assert not by_an_id(card)


# FLOW-F24: resuming a run that stopped by an error names it as the History does, with its automation.
@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_resuming_a_run_names_its_automation_and_when_it_started(language):
    ran = make_run(make_flow("Welcome"), status="failed", started_at=STARTED)
    card = card_for("flow.run.retry", {"id": str(ran.id)}, language)
    assert values(card) == {"id": f"Welcome · {WHEN[language]}"}
    assert not by_an_id(card)


# FLOW-F29: answering a question an automation asked names it by what it asks.
@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_answering_a_question_names_it_by_what_it_asks(language):
    from apps.flow.models import Question

    flow = make_flow("Refunds", trigger_kind="manual", steps=[{"id": "s1", "kind": "ask", "title": "x"}])
    asking = make_run(flow, status="asking", started_at=STARTED)
    question = Question.objects.create(
        run=asking, flow=flow, step_id="s1", title="Refund 15 € to Ana?", expires_at=STARTED + dt.timedelta(hours=72)
    )
    card = card_for("flow.question.answer", {"id": str(question.id), "approve": True}, language)
    assert values(card) == {"id": "Refund 15 € to Ana?", "approve": True}
    assert not by_an_id(card)


@pytest.mark.django_db
def test_a_record_the_person_may_not_read_is_left_out_never_by_its_id():
    """Someone who may only answer questions is shown no automation nor run (Automations is not theirs to read): the
    card leaves the run out."""
    ran = make_run(make_flow("Welcome"), status="failed", started_at=STARTED)
    answering = ctx_for(language="es", permissions={"flow.answer"})
    card = card_for("flow.run.retry", {"id": str(ran.id)}, "es", ctx=answering)
    assert values(card) == {}
    assert not by_an_id(card)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_of_another_business_is_left_out_never_by_its_id(hub_a, hub_b, monkeypatch):
    """Each business reads its own automations: one of business B named to business A's assistant is not there."""
    monkeypatch.setattr(context, "_test_fallback", None)
    with use_hub(hub_b):
        theirs = make_flow("Theirs")
    with use_hub(hub_a):
        mine = make_flow("Mine")
        ours = ctx_for(scope=Scope("host", hub_a.slug), language="es")
        assert values(card_for("flow.flow.set_enabled", {"id": str(theirs.id), "enabled": False}, "es", ctx=ours)) == {
            "enabled": False
        }
        assert values(card_for("flow.flow.set_enabled", {"id": str(mine.id), "enabled": False}, "es", ctx=ours)) == {
            "id": "Mine",
            "enabled": False,
        }

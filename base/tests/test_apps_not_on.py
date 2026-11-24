"""What the assistant knows of the business's apps that are not on (hub#2178).

Asked for what an app that is off does, the model was offered none of its tools and was never told the app existed: to
«quiero gestionar reservas» it answered it could not; asked for the salon's opening hours with Schedules off, it read
the staff's working hours; asked to start the online booking page with Online booking off, it turned off the automatic
confirmation of Appointments and said the page was running. Now an app not on whose name the person's words say, or the
model's searches, is named in the instructions with its state and what it is for, as ``base.app.get`` reads it, when it
has a tool among the places a turn gives with every app on; whoever may turn apps on is offered ``base.app.enable``,
whose card asks before it does. What the apps on already do names nothing and adds no tool. The app's own tools stay
out of the turn until it is on (``base.assistant.tools.catalog``), and every tool the turn offered keeps its place.
"""

import dataclasses
import json

import pytest
from live import assistant as shared
from live.context import OperationContext
from live.operations import get

from base import activation, assistant, entitlement, home
from base.models import Membership
from base.models.activation import AppActivation
from base.permissions import permissions_for
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.assistant_context import owner_of_a
from base.tests.test_app_activation import set_rows
from base.tests.test_assistant_asks import assert_offered_or_found
from base.tests.test_assistant_tool_search import turn, user
from base.tests.test_services_assistant import asked, call

__all__ = ["in_business_a"]

pytestmark = HUB_DB

ENABLE = "base.app.enable"
#: A hair salon just born with Services: what Services needs comes along with it, every other app is off.
SALON = {"service": "on*", "tax": "on", "staff": "on", "customer": "on"}
#: The same salon with Appointments on, and what it needs.
WITH_APPOINTMENTS = {**SALON, "appointment": "on*", "schedule": "on"}

HOURS = (
    "¿Qué horario tengo puesto en la peluquería? Si es el que viene de serie, déjalo confirmado, que de momento nos "
    "vale."
)
ONLINE = (
    "Quiero que las clientas puedan pedir cita desde el móvil. Ponme en marcha la página de reservas, pero que las "
    "citas me lleguen para confirmarlas yo."
)
#: What a person said, the apps on in the business, and the app off that does what was asked.
REPORTED = [
    ("es", "quiero gestionar reservas", SALON, "reservation"),
    ("es", "apunta una cita", SALON, "appointment"),
    ("en", "I want to manage reservations", SALON, "reservation"),
    ("en", "book an appointment", SALON, "appointment"),
    ("es", HOURS, SALON, "schedule"),
    ("es", ONLINE, WITH_APPOINTMENTS, "online_booking"),
]
IDS = ["reservas", "cita", "reservations", "appointment", "hours", "online-booking"]
#: A restaurant with what it uses every day on, and Reservations, Appointments, Price Lists and the rest off.
RESTAURANT = {
    label: "on"
    for label in ("sale", "table", "kitchen", "inventory", "cash_register", "payment", "invoice", "verifactu",
                  "customer", "tax", "printing", "modifier", "staff", "schedule")
}
#: What a business asks every day of the apps it has on: no app off is named nor any switch offered. The prices are of
#: Services or of the products («precio» is a word of Price Lists too, which stays off).
DAILY = [
    *((SALON, said) for said in (
        "gracias", "hola", "¿cuántos servicios tengo?", "crea el servicio Corte de pelo a 15 €",
        "da de alta a la clienta Ana López", "¿qué empleados tengo?", "¿cómo se llama mi negocio?",
        "añade a Marta como empleada", "¿qué IVA tienen mis servicios?", "sube el precio del tinte a 40 €",
        "borra el servicio Peinado", "cambia el precio del corte a 18 €", "¿qué clientas tengo?",
        "pon a Laura en el servicio de mechas", "apúntale el teléfono 600123123 a Ana",
    )),
    *((RESTAURANT, said) for said in (
        "¿cuánto vendí hoy?", "abre la mesa 4", "añade dos cafés a la mesa 2", "sube un 5 % las bebidas",
        "da de alta la tónica a 2,50 €", "cambia el precio del café a 1,50 €", "¿qué mesas están libres?",
        "¿a qué hora abrimos el sábado?", "¿qué camareros tengo?", "pon la hamburguesa agotada",
    )),
]
#: How the instructions say the apps named, and what the model does with them, to whoever may turn apps on and to
#: anyone else.
HEADER = "Apps not on whose tools would do what was asked (their tools are yours only once the app is on):"
DOES_IT = (
    "If one of them does it and none of your tools does, say that app does it and its state, and never try it with "
    "another tool."
)
TURN_ON = (
    " Off: offer to turn it on with `base__app__enable`, whose card asks the person, then go on with what they asked."
    " Blocked: a paid app the business has no right to, bought on erplora.com. Creating: on in a moment. Failed: it is"
    " tried again in Apps."
)
ASK_WHO_RUNS_IT = " Whoever runs the business turns it on in Apps."


def read_app(context, app: str) -> dict:
    """The app as the assistant reads it (``base.app.get``), in the person's language."""
    op = get("base.app.get")
    return op(context, op.input(app=app)).model_dump(mode="json")


def offered(plan: dict) -> list[str]:
    return [tool["name"] for tool in plan["tools"]]


def of_app(names: list[str], label: str) -> list[str]:
    return [name for name in names if name.startswith(f"{label}{shared.SEPARATOR}")]


def said_off(context, label: str) -> str:
    """How the instructions name an app that is not on: its name, its state and what it is for."""
    app = read_app(context, label)
    return f"- «{app['name']}» ({app['state']}): {app['summary']}"


def ranked_for(context, said: str) -> list[str]:
    """The tools a turn offers ``context`` for ``said`` by relevance alone, with the search last."""
    tools = assistant.tools.catalog(context)
    return [shared.tool_name(op.name) for op in assistant.relevance.relevant(tools, [said], context.language)]


def person(make_user, role: str, language: str = "es") -> OperationContext:
    member = make_user(f"p-{role}", host=A.key, role=role)
    return OperationContext(scope=A, actor=member, permissions=permissions_for(member, A), language=language)


def test_reading_an_app_says_what_it_is_for_in_the_persons_language(make_user):
    """What the Apps screen says of each app (its ``summary``), so the model tells it as the screen does."""
    set_rows(**SALON)
    owner = owner_of_a(make_user, "es")
    app = read_app(owner, "schedule")
    assert (app["name"], app["state"]) == ("Horarios", "off")
    assert app["summary"].startswith("Tu horario de apertura")
    assert read_app(dataclasses.replace(owner, language="en"), "schedule")["summary"].startswith("Your opening hours")


@pytest.mark.parametrize(("language", "said", "on", "app"), REPORTED, ids=IDS)
def test_what_an_app_off_does_names_it_and_offers_to_turn_it_on(make_user, language, said, on, app):
    set_rows(**on)
    context = owner_of_a(make_user, language)
    assert app not in assistant.tools.active_apps(A)  # the case reported: the app that does it is off
    plan = turn(context, user(said))
    assert said_off(context, app) in plan["instructions"]
    assert shared.tool_name(ENABLE) in offered(plan)
    assert of_app(offered(plan), app) == []  # its tools wait until it is on


@pytest.mark.parametrize(("language", "said", "on", "app"), REPORTED, ids=IDS)
def test_with_the_app_on_nothing_is_said_of_it_and_its_tools_are_offered_or_found(make_user, language, said, on, app):
    """Turned on (what ``base.app.enable`` brings along comes with it), the same words reach its tools, and the turn
    says nothing of an app off for them."""
    needs = activation.needs([app], activation.module_graph())
    set_rows(**({label: "on" for label in needs} | on | {app: "on*"}))
    context = owner_of_a(make_user, language)
    plan = turn(context, user(said))
    assert f"«{read_app(context, app)['name']}» (" not in plan["instructions"]
    tools = assistant.tools.catalog(context)
    first = {"reservation": "reservation.reservation.list", "appointment": "appointment.appointment.create",
             "schedule": "schedule.week.confirm", "online_booking": "online_booking.settings.update"}[app]
    tasks = {"reservation": "ver las reservas", "appointment": "crear una cita", "schedule": "confirmar el horario",
             "online_booking": "activar la página de reservas online"}
    assert_offered_or_found(tools, first, said, tasks[app], language)


def said_yes(context, said: str, write: str, app: str) -> dict:
    """The round after the person's yes to the card of ``write`` on ``app``, asked for in reply to ``said``."""
    switch = call(write, {"app": app})
    op = get("base.assistant.turn")

    def answer(pending, decision=None):
        given = op.input(messages=[user(said), asked(switch)], pending=pending, decision=decision)
        return op(context, given).model_dump(mode="json")

    drawn = answer([switch])
    assert drawn["confirm"] is not None
    plan = answer(drawn["pending"], {"call_id": switch["call_id"], "accepted": True, "typed": "CONFIRMAR"})
    assert plan["executed"][0]["outcome"] == "ok"
    return plan


def test_once_the_yes_turns_the_app_on_the_same_request_has_its_tools(make_user):
    """The card of ``base.app.enable`` answered, the round that follows offers the app's tools for what was asked, not
    only the next message: the model goes on with it, and is told of no app off."""
    set_rows(**SALON)
    plan = said_yes(owner_of_a(make_user, "es"), "quiero gestionar reservas", ENABLE, "reservation")
    assert json.loads(plan["append"][0]["content"])["state"] == "on"
    assert of_app(offered(plan), "reservation") != []
    assert HEADER not in plan["instructions"]


def test_once_the_yes_turns_the_app_off_the_round_that_follows_offers_none_of_its_tools(make_user):
    """What the person just turned off is no app to offer back, and its tools run no more."""
    set_rows(**{label: "on" for label in activation.module_graph()})
    context = owner_of_a(make_user, "es")
    said = "quita Tareas del menú"
    assert of_app(offered(turn(context, user(said))), "task") != []  # positive control: on, they are offered
    plan = said_yes(context, said, "base.app.disable", "task")
    assert json.loads(plan["append"][0]["content"])["state"] == "off"
    assert of_app(offered(plan), "task") == []
    assert HEADER not in plan["instructions"]


def test_once_the_yes_tries_a_failed_app_again_the_round_that_follows_reads_it_anew(make_user):
    set_rows(**{label: "on" for label in activation.module_graph()})
    AppActivation.objects.filter(host=A.key, app="appointment").update(state=activation.FAILED)
    activation.forget(A.key)
    context = owner_of_a(make_user, "es")
    plan = said_yes(context, "la app de citas no se pudo activar, inténtalo otra vez", "base.app.retry", "appointment")
    state = json.loads(plan["append"][0]["content"])["state"]
    assert (state, of_app(offered(plan), "appointment") != []) in {("on", True), ("creating", False)}
    assert HEADER not in plan["instructions"]


def test_who_runs_the_business_is_told_the_app_and_what_to_do_with_it(make_user):
    set_rows(**SALON)
    context = owner_of_a(make_user, "es")
    told = "\n".join([HEADER, said_off(context, "appointment"), DOES_IT + TURN_ON])
    assert told in turn(context, user("apunta una cita"))["instructions"]


@pytest.mark.parametrize("role", [Membership.Role.MANAGER, Membership.Role.EMPLOYEE])
def test_whoever_may_not_turn_apps_on_is_told_the_app_and_offered_no_switch(make_user, role):
    """The app is named so they know it exists; who runs the business turns it on (BASE-F24)."""
    set_rows(**SALON)
    context = person(make_user, role)
    plan = turn(context, user("apunta una cita"))
    assert "\n".join([HEADER, said_off(context, "appointment"), DOES_IT + ASK_WHO_RUNS_IT]) in plan["instructions"]
    assert shared.tool_name(ENABLE) not in offered(plan)
    assert shared.tool_name(ENABLE) not in plan["instructions"]


def test_an_app_out_of_the_plan_is_named_as_blocked_and_never_offered_on(make_user, monkeypatch):
    set_rows(**{label: "on" for label in activation.module_graph()})
    monkeypatch.setattr(entitlement, "blocked_apps", lambda scope: frozenset({"appointment"}))
    context = owner_of_a(make_user, "es")
    plan = turn(context, user("apunta una cita"))
    assert said_off(context, "appointment").startswith("- «Citas» (blocked): ")
    assert said_off(context, "appointment") in plan["instructions"]
    assert shared.tool_name(ENABLE) not in offered(plan)


@pytest.mark.parametrize("state", [activation.CREATING, activation.FAILED])
def test_an_app_being_set_up_or_that_failed_is_named_with_its_state_and_not_offered_on(make_user, state):
    set_rows(**{label: "on" for label in activation.module_graph()})
    AppActivation.objects.filter(host=A.key, app="appointment").update(state=state)
    activation.forget(A.key)
    context = owner_of_a(make_user, "es")
    plan = turn(context, user("apunta una cita"))
    assert said_off(context, "appointment").startswith(f"- «Citas» ({state}): ")
    assert said_off(context, "appointment") in plan["instructions"]
    assert shared.tool_name(ENABLE) not in offered(plan)


def test_at_most_three_apps_not_on_are_named_the_best_first(make_user):
    """A salon just born has nearly every app off, and words can name many of them: the three whose tools rank first
    are enough to say which does it, and each one more costs tokens in every call of the request."""
    set_rows(tax="on")
    context = owner_of_a(make_user, "es")
    said = "crea una reserva, una cita, una tarea y una factura"
    called = {"reservation", "online_booking", "appointment", "task", "invoice"}  # the apps it says by their names
    shown = {config.label for config in home.shown_modules()}
    every = assistant.tools.catalog(context, active_labels={*shown, "base"})
    ranked = assistant.relevance.relevant(every, [said], "es")
    best = list(dict.fromkeys(op.app_label for op in ranked if op.app_label in called))
    assert len(best) > 3  # positive control: more than three have a tool among the places
    text = turn(context, user(said))["instructions"]
    assert [app for app in best if said_off(context, app) in text] == best[:3]


@pytest.mark.parametrize(("language", "said", "on", "app"), REPORTED, ids=IDS)
def test_the_switch_goes_last_before_the_search_and_no_tool_loses_its_place(make_user, language, said, on, app):
    """Where the words already bring ``base.app.enable`` it stays in its place and is not added again."""
    set_rows(**on)
    context = owner_of_a(make_user, language)
    ranked = ranked_for(context, said)
    switch = shared.tool_name(ENABLE)
    expected = ranked if switch in ranked else [*ranked[:-1], switch, ranked[-1]]
    assert offered(turn(context, user(said))) == expected


@pytest.mark.parametrize(("on", "said"), DAILY, ids=[said for _, said in DAILY])
def test_what_the_apps_on_do_names_no_app_off_and_offers_the_same_tools(make_user, on, said):
    """«¿cuántos servicios tengo?» in a salon with Services on is no request of an app off, though an app off has a tool
    among the places its words give with every app on: the turn is as it was."""
    set_rows(**on)
    context = owner_of_a(make_user, "es")
    ranked = ranked_for(context, said)
    plan = turn(context, user(said))
    assert HEADER not in plan["instructions"]
    assert offered(plan) == ranked


def test_an_app_off_the_models_search_finds_is_named_in_the_round_that_follows(make_user):
    """Words that do not name Reservations («lo del sábado») leave it unsaid; the task the model searched for names it,
    as the search brings the tools it finds to the next round."""
    set_rows(**SALON)
    context = owner_of_a(make_user, "es")
    said = user("ayúdame con lo del sábado")
    assert "«Reservas» (" not in turn(context, said)["instructions"]  # positive control: the words alone name it not
    search = call("base.assistant.find_tools", {"query": "crear una reserva de mesa"}, "s1")
    plan = turn(context, said, asked(search), {"role": "tool", "tool_call_id": "s1", "content": "{}"})
    assert said_off(context, "reservation") in plan["instructions"]

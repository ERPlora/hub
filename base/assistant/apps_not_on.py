"""The business's apps that are not on that a request names (``named``), what the model hears of them (``said``) and
the switch a turn offers for them (``with_switch``).

A turn offers only the tools of the apps on (``base.assistant.tools.catalog``), so the model never knew that an app off
did what was asked: it said it could not, or did something else with the tools it had. An app not on is named when the
person's words, or the model's searches, say its name (``_names``) and it has a tool among the places a turn gives with
every app on: as ``base.app.get`` reads it (its name, its state and what it is for), best first and ``NAMED`` at most.
Whoever may turn apps on is offered ``base.app.enable``, whose card asks before it does. Its own tools stay out until it
is on. What the apps on do names none: «¿cuántos servicios tengo?» says no app off, though one of their tools may rank
among those places.
"""

from collections.abc import Iterable
from functools import cache

from django.apps import apps as django_apps
from django.utils import translation
from live.assistant import stems, tool_name
from live.context import OperationContext
from live.operations import Operation, get

from base import home
from base.assistant import relevance, tools

#: The apps not on a turn names at most: the ones whose tools rank first say which does it, and each one more is
#: tokens in every call of the request.
NAMED = 3
ENABLE = "base.app.enable"
#: The writes that turn an app on or off: once one runs, the round that follows offers the tools of the apps on then.
SWITCHES = frozenset({ENABLE, "base.app.disable", "base.app.retry"})

HEADER = "Apps not on whose tools would do what was asked (their tools are yours only once the app is on):"
DOES_IT = (
    "If one of them does it and none of your tools does, say that app does it and its state, and never try it with "
    "another tool."
)
TURN_ON = (
    f" Off: offer to turn it on with `{tool_name(ENABLE)}`, whose card asks the person, then go on with what they"
    " asked. Blocked: a paid app the business has no right to, bought on erplora.com. Creating: on in a moment. Failed:"
    " it is tried again in Apps."
)
ASK_WHO_RUNS_IT = " Whoever runs the business turns it on in Apps."


def named(ctx: OperationContext, texts: Iterable[str], searched: Iterable[str]) -> list[dict]:
    """The apps not on whose name ``texts`` or the model's ``searched`` tasks say, with a tool among a turn's places for
    them against what ``ctx``'s person would hold with every app on: best first and ``NAMED`` at most, as
    ``base.app.get`` reads each. None when no app off is said."""
    texts, searched = list(texts), list(searched)
    words = set().union(*(stems(text) for text in [*texts, *searched]))
    on = tools.active_apps(ctx.scope)
    not_on = {config.label for config in home.shown_modules()} - set(on)
    called = {label for label in not_on if not words.isdisjoint(_names(label, ctx.language))}
    if not called:
        return []
    every = tools.catalog(ctx, active_labels={*on, *not_on})
    ranked = relevance.relevant(every, texts, ctx.language, searched=searched)
    labels = list(dict.fromkeys(op.app_label for op in ranked if op.app_label in called))[:NAMED]
    read = get("base.app.get")
    return [read(ctx, read.input(app=label)).model_dump(mode="json") for label in labels]


@cache
def _names(label: str, language: str) -> frozenset[str]:
    """The stems of app ``label``'s name in ``language``, as the person's menu says it: compared with the words as they
    are said, never with what they also mean («precio» is no Price Lists; «reservas» is Reservations)."""
    with translation.override(language):
        return frozenset(stems(str(django_apps.get_app_config(label).verbose_name)))


def said(ctx: OperationContext, apps: list[dict]) -> str:
    """The lines of the instructions on ``apps`` (``named``), each with its state and what it is for, and what the model
    does with them: whoever may turn apps on (``base.app.enable``'s permission) is offered it, anyone else is told who
    does. Nothing when there are none."""
    if not apps:
        return ""
    lines = [HEADER, *(f"- «{app['name']}» ({app['state']}): {app['summary']}" for app in apps)]
    return "\n".join([*lines, DOES_IT + (TURN_ON if ctx.has(get(ENABLE).permission) else ASK_WHO_RUNS_IT)])


def with_switch(offered: list[Operation], person: dict[str, Operation], apps: list[dict]) -> list[Operation]:
    """``offered`` with ``base.app.enable`` before the search of the rest, its last, when one of ``apps`` is off, the
    person may turn it on (it is in ``person``, their catalogue) and the turn does not offer it already: every tool
    offered keeps its place."""
    if not offered or ENABLE not in person or any(op.name == ENABLE for op in offered):
        return offered
    if not any(app["state"] == "off" for app in apps):
        return offered
    return [*offered[:-1], person[ENABLE], offered[-1]]

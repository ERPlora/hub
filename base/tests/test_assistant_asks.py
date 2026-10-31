"""Layer 1 of the assistant's QA (docs plan 2026-10-31, the assistant's knowledge and QA, §1.4): deterministic, with no
model and no network, in every pull request.

Every tool of an app listed in ``LIVE_ASSISTANT_ASKS_REQUIRED`` says what a person types to ask for it (its ``asks``,
``live.E020``), and each of those phrases, ranked exactly as a chat turn ranks (``base.assistant.relevant``: the same
``ALWAYS`` first, the same ``APP_WORDS``), brings its tool among the first ten offered, against the real catalogue of
each role of the Hub (``base.assistant.catalog`` of a member of business ``a``, which has every module on: the largest
catalogue a role can have). What a role may not run is not in its catalogue at all. An app joins the list in the same
pull request that completes its asks; the ones still missing are reported per app (``AsksBacklog``), never failed.
"""

import warnings
from collections import Counter
from collections.abc import Iterable

import pytest
from django.conf import settings
from live import assistant as shared
from live.assistant_qa import Miss, misses, uncovered
from live.context import OperationContext, Scope
from live.operations import MIN_ASKS, Operation, registry

from base import approvals, assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
LANGUAGES = ("en", "es")
ROLES = tuple(Membership.Role)
#: The apps whose tools all say their asks (``live.E020``): read from the settings, so each app that joins is tested.
LISTED = tuple(settings.LIVE_ASSISTANT_ASKS_REQUIRED)
#: How far down the tools a turn offers an ask may bring its own: ``ALWAYS`` takes the first places.
TOP = 10

#: A real write of ``base`` per role, and whether the role holds it: who runs the business turns apps on and off and
#: deletes files; a manager and an employee do neither (``base.administer_hub``, ``base.delete_files``), while every
#: role keeps its own profile (``base.view_home``): their catalogue is not merely empty.
WITNESSES = {
    "base.app.enable": {Membership.Role.OWNER, Membership.Role.ADMIN},
    "base.file.delete": {Membership.Role.OWNER, Membership.Role.ADMIN},
    "base.profile.update": set(ROLES),
}

_found: dict[tuple[str, tuple[str, ...]], list[Miss]] = {}


class AsksBacklog(UserWarning):
    """The tools of the apps not yet listed that say no asks, per app: the backlog of the fleet, never a failure."""


@pytest.fixture
def context_of(make_user):
    def of(role: str, language: str) -> OperationContext:
        user = make_user(f"qa-{role}", host=A.key, role=role)
        return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language=language)

    return of


def of_app(tool_name: str, label: str) -> bool:
    return tool_name.startswith(f"{label}{shared.SEPARATOR}")


def missed(tools: dict[str, Operation], language: str) -> list[Miss]:
    """``misses`` of ``tools`` as a turn ranks them, once per catalogue: the roles that hold the same tools share it."""
    key = (language, tuple(tools))
    if key not in _found:
        _found[key] = misses(tools, language=language, top=TOP, app_words=assistant.APP_WORDS, always=assistant.ALWAYS)
    return _found[key]


def backlog(tools: Iterable[Operation], language: str) -> Counter[str]:
    """How many of ``tools`` say no asks in ``language``, per app."""
    return Counter(name.split(shared.SEPARATOR)[0] for name in uncovered({op.name: op for op in tools}, language))


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("label", LISTED)
def test_each_ask_of_a_listed_app_brings_its_tool_among_the_first_ten(context_of, label, language, role):
    assert label in assistant.active_apps(A)  # on in business a: its tools are in the catalogue, the sweep is real
    tools = assistant.catalog(context_of(role, language))
    ranked = {name: op for name, op in tools.items() if op.app_label == label}
    if role == Membership.Role.OWNER:  # who runs the business holds every tool of an app on: never an empty sweep
        assert ranked, f"the owner's catalogue has no tool of {label!r}: none of its asks would be checked"
    # Each tool of the app this role holds is ranked by MIN_ASKS phrases or more of its own in this language.
    checked = {name: len(shared.asks_of(op).get(language, ())) for name, op in ranked.items()}
    assert {name: count for name, count in checked.items() if count < MIN_ASKS} == {}
    assert [name for name in uncovered(tools, language) if of_app(name, label)] == []
    assert [miss for miss in missed(tools, language) if of_app(miss.tool_name, label)] == []


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", ROLES)
def test_a_tool_the_role_may_not_run_is_not_in_its_catalogue(context_of, role):
    ctx = context_of(role, "en")
    tools = assistant.catalog(ctx)
    on = assistant.active_apps(A)
    lacked = {
        name
        for name, op in registry.items()
        if op.app_label in on
        and assistant.is_tool(op)
        and not ctx.has(op.permission)
        and approvals.label_of(op) is None  # a write a manager may approve is theirs too, as its button is
    }
    assert lacked.isdisjoint(tools), sorted(lacked & set(tools))
    for name, holders in WITNESSES.items():
        assert assistant.is_tool(registry[name]), name  # a tool: only the role can leave it out
        assert (name in tools) is (role in holders), name
        assert (name in lacked) is (role not in holders), name


def test_the_tools_still_without_asks_are_reported_per_app_and_none_of_a_listed_app():
    """The backlog over every tool of the Hub (a business with every app on, as its owner sees it): reported, not
    failed, for the apps not listed yet; a listed app has none."""
    tools = [op for op in registry.values() if assistant.is_tool(op)]
    by_language = {language: backlog(tools, language) for language in LANGUAGES}
    for language, counted in by_language.items():
        assert not set(counted) & set(LISTED), (language, counted)
    totals = Counter(op.app_label for op in tools)
    lines = [
        f"{label} {by_language['en'].get(label, 0)}/{by_language['es'].get(label, 0)} of {totals[label]}"
        for label in sorted(set().union(*by_language.values()))
    ]
    said = "; ".join(lines) or "none"
    warnings.warn(AsksBacklog(f"Assistant tools without asks per app (en/es of its tools): {said}"), stacklevel=1)

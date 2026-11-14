"""Layer 1 of the assistant's QA: deterministic, with no
model and no network, in every pull request.

Every tool of an app listed in ``LIVE_ASSISTANT_ASKS_REQUIRED`` says what a person types to ask for it (its ``asks``,
``live.E020``), and each of those phrases, ranked exactly as a chat turn ranks (``base.assistant.RANKING``: the same
``ALWAYS`` first, the same ``APP_WORDS``, the Hub's own ``SYNONYMS`` and ``HOWTO``), brings its tool among the first ten
offered, against the real catalogue of each role of the Hub (``base.assistant.catalog`` of a member of business ``a``,
which has every module on: the largest catalogue a role can have). What a role may not run is not in its catalogue at
all. An app joins the list in the same pull request that completes its asks, and stays in it while any of its tools
says one; the ones still missing are reported per app (``AsksBacklog``), never failed. How many asks of each listed
app reach their tool without their own words (``own_asks=False``: how a person's new phrase would) is reported too
(``AsksReach``), never failed. What an app's own test ranks as a person's words is none of its asks, nor one but for
a word, and no ask is a probe of layer 2 of its tool but for a word: either would measure the asks' own words.
"""

import dataclasses
import importlib
import json
import re
import unicodedata
import warnings
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from types import ModuleType

import pytest
from django.conf import settings
from live import assistant as shared
from live.assistant_qa import Miss, misses, report, uncovered
from live.checks import check_assistant_asks
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
    """The tools of the apps not yet listed that say no asks, per app: a backlog, never a failure."""


class AsksReach(UserWarning):
    """How many asks of each listed app bring their tool among the first ten without their own words, per language: how
    a person's new phrase would fare (``own_asks=False``), information and never a failure."""


def members(make_user, prefix: str) -> Callable[[str, str], OperationContext]:
    """``of(role, language)``: the context of a member of business ``a`` with ``role``, who asks in ``language``."""
    users = {}

    def of(role: str, language: str) -> OperationContext:
        if role not in users:  # one person per role, whatever the language they ask in
            users[role] = make_user(f"{prefix}-{role}", host=A.key, role=role)
        user = users[role]
        return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language=language)

    return of


@pytest.fixture
def context_of(make_user):
    return members(make_user, "qa")


def of_app(tool_name: str, label: str) -> bool:
    return tool_name.startswith(f"{label}{shared.SEPARATOR}")


def missed(tools: dict[str, Operation], language: str) -> list[Miss]:
    """``misses`` of ``tools`` as a turn ranks them, once per catalogue: the roles that hold the same tools share it."""
    key = (language, tuple(tools))
    if key not in _found:
        _found[key] = misses(tools, language=language, top=TOP, **assistant.RANKING)
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
    if role == Membership.Role.OWNER:  # who runs the business holds every tool of an app on: the sweep is whole
        assert set(ranked) == {name for name, op in registry.items() if op.app_label == label and assistant.is_tool(op)}
    # Each tool of the app this role holds is ranked by MIN_ASKS phrases or more of its own in this language.
    checked = {name: len(shared.asks_of(op).get(language, ())) for name, op in ranked.items()}
    assert {name: count for name, count in checked.items() if count < MIN_ASKS} == {}
    assert [name for name in uncovered(tools, language) if of_app(name, label)] == []
    assert [miss for miss in missed(tools, language) if of_app(miss.tool_name, label)] == []


def completed() -> set[str]:
    """The apps that completed their asks: every one of their tools says ``MIN_ASKS`` phrases or more in each
    language. The asks are the record of it, so the apps are written once, in ``LIVE_ASSISTANT_ASKS_REQUIRED``."""
    tools = [op for op in registry.values() if assistant.is_tool(op)]
    short = {
        op.app_label for op in tools for language in LANGUAGES if len(shared.asks_of(op).get(language, ())) < MIN_ASKS
    }
    return {op.app_label for op in tools} - short


def started() -> set[str]:
    """The apps with a tool that says any ask: asks are written in the pull request that lists their app, so an app
    taken off the list while its other tools still say theirs is seen."""
    return {op.app_label for op in registry.values() if assistant.is_tool(op) and any(shared.asks_of(op).values())}


def test_the_listed_apps_are_the_ones_that_completed_their_asks():
    """An app whose tools say asks is listed, and stays listed: one left out of ``LIVE_ASSISTANT_ASKS_REQUIRED``
    (forgotten, or taken off it to quiet the sweep when a new tool came without its asks) escapes the sweep; one listed
    without them all fails it (hub#1144)."""
    assert sorted(started() - set(LISTED)) == []
    assert sorted(set(LISTED) - completed()) == []


def test_live_asks_nothing_more_of_the_listed_apps():
    """``live.E020`` over the real settings: every tool of a listed app says two distinct phrases at least in each
    language, none empty, its own name nor longer than a chat line (``manage.py check`` fails otherwise)."""
    assert check_assistant_asks() == []


#: The probes of layer 2 (``tests/e2e/qa/assistant-probes.spec.ts``), every app and role: phrases nobody wrote as asks.
PROBES = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"


def comparable(text: str) -> str:
    """``text`` as layer 2 compares a probe with the asks (``tests/e2e/assistant-probes.ts`` ``normalized``): lower
    case, without accents, punctuation or extra spaces."""
    bare = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w]+|_", " ", bare).split())


def probe_phrases() -> dict[str, str]:
    return {
        comparable(probe["phrase"]): probe["id"]
        for path in sorted(PROBES.glob("*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    }


# ── What an app's own test of its asks ranks with (``apps/<app>/tests/test_assistant_asks.py`` imports them) ────────


#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a person's own words may bring their tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``. Its people are
    not ``context_of``'s, so a test may take both: an app's test imports this one alone, and its ``make_user`` is the
    one of the app's ``conftest.py``."""
    context_of = members(make_user, "asker")

    def of(role: str, language: str) -> dict[str, Operation]:
        return assistant.catalog(context_of(role, language))

    return of


def offered_to(tools: dict[str, Operation], phrase: str, language: str = "es", **ranking) -> list[str]:
    """The tools a turn in ``language`` offers for ``phrase``, best first, as ``base.assistant.RANKING`` ranks them, or
    with what ``ranking`` puts in its place (``synonyms=``…)."""
    return [op.name for op in shared.relevant(tools, [phrase], language, **{**assistant.RANKING, **ranking})]


def place_in(offered: list[str], name: str) -> int | None:
    """The place of ``name`` in ``offered`` (1 is first), ``None`` when it is not there."""
    return offered.index(name) + 1 if name in offered else None


def offered_place(tools: dict[str, Operation], name: str, phrase: str, language: str = "es", **ranking) -> int | None:
    """The place a turn offers ``name`` at for ``phrase`` (1 is first), ``None`` when it is not offered at all."""
    return place_in(offered_to(tools, phrase, language, **ranking), name)


def place_of_no_ask(tools: dict[str, Operation], name: str, phrase: str, language: str = "es") -> int | None:
    """``offered_place`` of a tool the person holds for a ``phrase`` that is none of its asks, in any language: every
    ask scores for the phrases that share its words, whatever the language of the turn."""
    assert name in tools  # positive control: the person holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for asks in shared.asks_of(tools[name]).values() for ask in asks}
    return offered_place(tools, name, phrase, language)


def assert_offered_with_room(
    tools: dict[str, Operation], name: str, phrase: str, language: str = "es", room: int = WITH_ROOM
) -> None:
    """That ``phrase``, a person's words and none of the asks of tool ``name``, brings it among the first ``room`` a
    turn offers."""
    place = place_of_no_ask(tools, name, phrase, language)
    assert place is not None and place <= room, place


def assert_reported_are_owner_probes(reported: Iterable[tuple[str, str]]) -> None:
    """Each ``(tool, phrase)`` an app's test reports is, word for word, the owner's Spanish probe of layer 2 of that
    tool (``owner.es.<tool>``): the phrases are the QA's, never written to fit."""
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in reported] == [f"owner.es.{name}" for name, _ in reported]


def test_no_ask_copies_a_qa_probe_or_names_a_qa_record():
    """The probes measure that the selection generalises: a probe written into its tool's
    asks ranks its own words and layer 2 skips it as a copy, and a record of the QA's data («Documentos QA/nota-qa.txt»,
    «Ordenador de oficina QA») is no phrase a business says: its «QA» scores for every probe that names one."""
    phrases = probe_phrases()
    assert len(phrases) > 100  # positive control: the probes of layer 2 are read
    assert comparable("¿Cuánto vendí hoy?") == "cuanto vendi hoy"
    copied, qa = [], []
    for op in registry.values():
        if not assistant.is_tool(op):
            continue
        for phrases_of in shared.asks_of(op).values():
            for ask in phrases_of:
                if comparable(ask) in phrases:
                    copied.append((op.name, ask, phrases[comparable(ask)]))
                if re.search(r"\bQA\b", ask):
                    qa.append((op.name, ask))
    assert copied == []
    assert qa == []


def alike(one: str, other: str) -> bool:
    """Whether two phrases, ``comparable``, are the same words but for one at most: one changed, added or dropped."""
    shorter, longer = sorted((comparable(one).split(), comparable(other).split()), key=len)
    if len(longer) - len(shorter) > 1:
        return False
    if len(longer) == len(shorter):
        return sum(word != said for word, said in zip(shorter, longer, strict=True)) <= 1
    return any(longer[:at] + longer[at + 1 :] == shorter for at in range(len(longer)))


def probes_of_layer_2() -> list[dict]:
    """Every probe of layer 2, as its file says it: its ``id``, ``tool``, ``role``, ``language`` and ``phrase``."""
    return [probe for path in sorted(PROBES.glob("*.json")) for probe in json.loads(path.read_text("utf-8"))["probes"]]


def asks_by_tool(label: str | None = None) -> dict[str, tuple[str, ...]]:
    """The asks of each tool of the Hub, or of app ``label``, in every language."""
    return {
        op.name: tuple(ask for phrases in shared.asks_of(op).values() for ask in phrases)
        for op in registry.values()
        if assistant.is_tool(op) and label in (None, op.app_label)
    }


def without_its_asks(tools: dict[str, Operation], name: str, language: str | None = None) -> dict[str, Operation]:
    """``tools`` with tool ``name`` saying no asks in ``language``, or in any language without one (its description and
    name stay): where a phrase would bring it without them, so an app's test shows that its asks, and not only its
    name, bring a person's own words."""
    op = tools[name]
    kept = {said: asks for said, asks in shared.asks_of(op).items() if language is not None and said != language}
    return {**tools, name: dataclasses.replace(op, ai=dataclasses.replace(op.ai_spec(), asks=kept))}


def nobodys_words(tools: dict[str, Operation], phrase: str, language: str = "es") -> bool:
    """Whether ``phrase`` is no probe of layer 2 and no ask in ``language`` of any tool of ``tools``: it measures the
    words, never a copy."""
    asks = {comparable(ask) for op in tools.values() for ask in shared.asks_of(op).get(language, ())}
    return comparable(phrase) not in probe_phrases() and comparable(phrase) not in asks


def assert_own_words(tools: dict[str, Operation], name: str, phrase: str, language: str) -> None:
    """That ``phrase`` is a person's own words for tool ``name``: no probe of layer 2, no ask of any tool, and no ask
    of ``name`` in any language but for a word."""
    assert name in tools  # positive control: the person holds the tool, so its place is known
    assert nobodys_words(tools, phrase, language), "it is a probe of layer 2 or an ask"
    said = [ask for asks in shared.asks_of(tools[name]).values() for ask in asks if alike(ask, phrase)]
    assert not said, ("it is an ask but for a word at most", said)


def assert_its_asks_bring(tools: dict[str, Operation], name: str, phrase: str, language: str) -> None:
    """That ``phrase``, in a person's own words (``assert_own_words``), brings ``name`` among the first ``TOP`` by its
    asks: with them it is there, ``without_its_asks`` in any language it is not. The test of an app that calls it for
    each of its tools sees any change to their asks (hub#1135, hub#1165)."""
    assert_own_words(tools, name, phrase, language)
    offered = offered_to(tools, phrase, language)
    assert name in offered[:TOP], ("its asks do not bring it", place_in(offered, name), offered[:TOP])
    unasked = offered_to(without_its_asks(tools, name), phrase, language)
    assert name not in unasked[:TOP], ("it comes without its asks", place_in(unasked, name))


def assert_its_asks_lift(tools: dict[str, Operation], name: str, phrase: str, language: str) -> None:
    """That ``phrase``, in a person's own words in ``language`` (``assert_own_words``), brings ``name`` among the first
    ``TOP``, and higher than it would without its asks in ``language`` (those in other languages kept). In English a
    tool's name and description, written in English too, bring many phrases on their own, and its Spanish asks say
    the same things: what its English asks add is the lift, so English asks overwritten or emptied fail here."""
    assert_own_words(tools, name, phrase, language)
    place = offered_place(tools, name, phrase, language)
    assert place is not None and place <= TOP, ("its asks do not bring it", place)
    unasked = offered_place(without_its_asks(tools, name, language), name, phrase, language)
    assert unasked is None or unasked > place, ("its asks in this language do not lift it", place, unasked)


def said_only_in_english(op: Operation) -> list[str]:
    """The words of ``op``'s English asks that nothing else of it says: no Spanish ask, nor its description or name,
    names what they name (``base.assistant.SYNONYMS`` included). Where there are none, no English phrase depends on
    its English asks, so no ranking can see them change; filler written over them is such a word."""
    asks = shared.asks_of(op)
    name = op.name.replace(".", " ").replace("_", " ")
    elsewhere = shared.stems(" ".join([*asks.get("es", ()), shared.description(op), name]))
    words = [word for ask in asks.get("en", ()) for word in re.findall(r"[\w'’-]+", ask)]
    return list(
        dict.fromkeys(
            word
            for word in words
            if (concepts := shared.asked([word], assistant.SYNONYMS).concepts)
            and all(concept.isdisjoint(elsewhere) for concept in concepts)
        )
    )


# ── The tests each app declares the same way: built here, assigned there ─────────────────────────────────────────
# An app assigns what these return to the name of its test (``test_… = own_words_test(OWN_WORDS, "es")``): pytest
# collects the test in the app's module, under that name and with the same ids, and takes the app's ``catalog_of``.

OWNER = Membership.Role.OWNER


def own_words_test(cases: list, language: str | None = None, *, ids: list[str] | None = None) -> Callable:
    """The test that each phrase of ``cases``, a person's own words for a tool of the app, brings it to the owner by its
    asks (``assert_its_asks_bring``): ``(name, phrase)`` said in ``language``, or ``(language, name, phrase)``."""
    if language is None:

        @pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
        @pytest.mark.parametrize(("language", "name", "phrase"), cases, ids=ids)
        def said_in_its_language(catalog_of, language, name, phrase):
            assert_its_asks_bring(catalog_of(OWNER, language), name, phrase, language)

        return said_in_its_language

    @pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
    @pytest.mark.parametrize(("name", "phrase"), cases, ids=ids)
    def said_in_one_language(catalog_of, name, phrase):
        assert_its_asks_bring(catalog_of(OWNER, language), name, phrase, language)

    return said_in_one_language


def english_words_test(cases: list) -> Callable:
    """The test that each ``(name, phrase)`` of ``cases``, a person's own words in English for a tool of the app, is
    lifted by the tool's English asks for the owner (``assert_its_asks_lift``)."""

    @pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
    @pytest.mark.parametrize(("name", "phrase"), cases)
    def lifted(catalog_of, name, phrase):
        assert_its_asks_lift(catalog_of(OWNER, "en"), name, phrase, "en")

    return lifted


def english_coverage_test(label: str, cases: list, also: Iterable[str] = ()) -> Callable:
    """The test that each tool of app ``label`` has a person's own words in English once: a ``(name, phrase)`` of
    ``cases``, or one of ``also`` (the app's English words written elsewhere). A tool added later without them would
    let its English asks change unseen."""

    def covered():
        tools = sorted(name for name, op in registry.items() if op.app_label == label and assistant.is_tool(op))
        assert sorted([name for name, _ in cases] + list(also)) == tools

    return covered


def said_in_spanish_too_test(names: Iterable[str]) -> Callable:
    """The test that the English asks of each tool of ``names`` say nothing its Spanish asks, description or name do
    not (``said_only_in_english``): no English phrase depends on them, so this is what sees them change."""

    @pytest.mark.parametrize("name", sorted(names))
    def said_in_spanish_too(name):
        assert said_only_in_english(registry[name]) == []

    return said_in_spanish_too


def reported_test(reported: list) -> Callable:
    """The test that each ``(name, phrase)`` of ``reported``, the owner's request of the real-model QA in Spanish, is
    offered its existing operation (``assert_offered_with_room``)."""

    @pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
    @pytest.mark.parametrize(("name", "phrase"), reported)
    def offered(catalog_of, name, phrase):
        assert_offered_with_room(catalog_of(OWNER, "es"), name, phrase)

    return offered


def probes_test(probes: list[dict], label: str) -> Callable:
    """The test that each probe of layer 2 of app ``label`` in ``probes``, the owner's in Spanish, is offered its tool
    without being one of its asks (``assert_offered_with_room``): a tool that a new ask elsewhere pushes out of the
    first half of the ones a turn offers fails here before the real-model QA sees it."""

    @pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
    @pytest.mark.parametrize("probe", probes, ids=[probe["id"] for probe in probes])
    def offered(catalog_of, probe):
        assert (probe["app"], probe["role"], probe["language"]) == (label, "owner", "es")
        assert_offered_with_room(catalog_of(OWNER, probe["language"]), probe["tool"], probe["phrase"])

    return offered


def by_group_test(cases: list) -> Callable:
    """The test that each ``(name, phrase, word)`` of ``cases``, a request in Spanish, brings its tool among the first
    ``TOP`` by the group of ``base.assistant.SYNONYMS`` that says ``word``, and not without that group."""

    @pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
    @pytest.mark.parametrize(("name", "phrase", "word"), cases)
    def by_its_group(catalog_of, name, phrase, word):
        tools = catalog_of(OWNER, "es")
        assert comparable(phrase) not in probe_phrases()
        assert_offered_with_room(tools, name, phrase, room=TOP)
        without = tuple(group for group in assistant.SYNONYMS if word not in group)
        assert len(without) == len(assistant.SYNONYMS) - 1  # positive control: exactly its group is left out
        assert name not in offered_to(tools, phrase, synonyms=without)[:TOP]

    return by_its_group


#: A person's own words in English for ``verifactu.chain.validate``, and what its English asks become when someone
#: overwrites them with filler: the positive control of ``assert_its_asks_lift``.
LIFTED = ("verifactu.chain.validate", "the accountant fears it's broken somewhere, verify every link")
FILLER = ("zzqxfillera", "zzqxfillerb")


def with_asks(tools: dict[str, Operation], name: str, language: str, asks: tuple[str, ...]) -> dict[str, Operation]:
    """``tools`` with tool ``name`` saying ``asks`` in ``language`` and the rest of its asks as they are."""
    op = tools[name]
    said = {**shared.asks_of(op), language: asks}
    return {**tools, name: dataclasses.replace(op, ai=dataclasses.replace(op.ai_spec(), asks=said))}


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_english_asks_overwritten_with_filler_no_longer_lift_their_tool(context_of):
    """The English asks of a tool, overwritten with filler while its Spanish ones stay, leave a person's English words
    where the tool's name, description and Spanish asks put them: ``assert_its_asks_lift`` fails, as an app's test of
    its English phrases does (hub#1216: before it, only its Spanish asks were measured)."""
    name, phrase = LIFTED
    tools = assistant.catalog(context_of(Membership.Role.OWNER, "en"))
    assert_its_asks_lift(tools, name, phrase, "en")
    with pytest.raises(AssertionError):
        assert_its_asks_lift(with_asks(tools, name, "en", FILLER), name, phrase, "en")
    assert shared.asks_of(without_its_asks(tools, name, "en")[name]) == {"es": shared.asks_of(tools[name])["es"]}


def test_a_word_only_the_english_asks_say_is_found():
    """``said_only_in_english``: the English asks of ``invoice.invoice.print`` say what its Spanish asks and its
    description already do, so filler written over them is a word nothing else of the tool says."""
    op = registry["invoice.invoice.print"]
    assert said_only_in_english(op) == []
    asks = {**shared.asks_of(op), "en": FILLER}
    overwritten = dataclasses.replace(op, ai=dataclasses.replace(op.ai_spec(), asks=asks))
    assert said_only_in_english(overwritten) == list(FILLER)


def near_copies(asks: dict[str, tuple[str, ...]], probes: Iterable[dict]) -> list[tuple[str, str, str]]:
    """The asks (of each tool, in ``asks``) that are a probe of their own tool but for one word (``alike``), as (tool,
    ask, probe): layer 2 compares a probe with the asks of its tool only, so another tool's phrase one word off is
    another request («abre la caja», «cierra la caja»)."""
    return [
        (probe["tool"], ask, probe["id"])
        for probe in probes
        for ask in asks.get(probe["tool"], ())
        if alike(ask, probe["phrase"])
    ]


#: What ``pytest.param`` makes: a case with its own marks or id, whose ``values`` are the ones the test receives.
PARAM = type(pytest.param())


def ranked_phrases(module: ModuleType) -> list[tuple[str, str | None, str]]:
    """What the tests of ``module`` rank as a person's words, as (test, tool, phrase): each value of a parametrized
    ``phrase``, with the tool of the ``name`` beside it (``None`` without one), and the ``phrase`` of each parametrized
    probe of layer 2, with its ``tool``."""
    found = []
    for test, function in vars(module).items():
        if not test.startswith("test_") or not callable(function):
            continue
        for mark in getattr(function, "pytestmark", ()):
            if mark.name != "parametrize":
                continue
            names, cases = mark.args[:2]
            names = [name.strip() for name in names.split(",")] if isinstance(names, str) else list(names)
            for case in cases:
                values = case.values if isinstance(case, PARAM) else case if len(names) > 1 else (case,)
                bound = dict(zip(names, values, strict=True))
                if isinstance(bound.get("phrase"), str):
                    found.append((test, bound.get("name"), bound["phrase"]))
                found += [
                    (test, value.get("tool"), value["phrase"])
                    for value in bound.values()
                    if isinstance(value, dict) and isinstance(value.get("phrase"), str)
                ]
    return found


def tautologies(module: ModuleType, asks: dict[str, tuple[str, ...]]) -> list[tuple[str, str, str]]:
    """The phrases the tests of ``module`` rank as a person's words (``ranked_phrases``) that are one of ``asks`` (the
    asks of the app's tools), or one of their tool's asks but for one word (``alike``), as (test, phrase, ask)."""
    every = {comparable(ask): ask for said in asks.values() for ask in said}
    found = []
    for test, tool, phrase in ranked_phrases(module):
        ask = every.get(comparable(phrase)) or next((ask for ask in asks.get(tool, ()) if alike(ask, phrase)), None)
        if ask is not None:
            found.append((test, phrase, ask))
    return found


def test_an_ask_that_is_a_probe_of_its_tool_but_for_one_word_is_a_copy():
    """Positive control of the guard below, on a probe and asks of its own: an ask that says the probe of its tool with
    a word changed, added or dropped is caught as the copy it is; one two words off, or another tool's, is another
    request («abre la caja» is no copy of «cierra la caja»)."""
    probe = {"id": "qa.example", "tool": "x.menu.list", "phrase": "¿Qué menús hay dados de alta?"}
    asks = {
        "x.menu.list": (
            "que menus hay dados de alta",  # the probe itself, comparable
            "¿qué menús hay dados de baja?",  # a word changed
            "¿qué menús hay dados de alta ahora?",  # a word added
            "¿qué menús hay de alta?",  # a word dropped
            "¿qué menús hay dados de alta ahora mismo?",  # two words: another phrase
            "¿cuántos menús tenemos?",
        ),
        "x.menu.delete": ("¿qué menús hay dados de baja?",),  # another tool's: another request
    }
    assert near_copies(asks, [probe]) == [
        ("x.menu.list", "que menus hay dados de alta", "qa.example"),
        ("x.menu.list", "¿qué menús hay dados de baja?", "qa.example"),
        ("x.menu.list", "¿qué menús hay dados de alta ahora?", "qa.example"),
        ("x.menu.list", "¿qué menús hay de alta?", "qa.example"),
    ]


def test_no_ask_is_a_qa_probe_of_its_tool_but_for_one_word():
    """``test_no_ask_copies_a_qa_probe_or_names_a_qa_record`` compares the exact text; an ask that is its tool's probe
    with one word changed ranks the probe by the ask's own words just the same, and layer 2
    (``tests/e2e/assistant-probes.ts``), which skips only the exact copies, measures nothing with it (hub#1135)."""
    probes = probes_of_layer_2()
    asks = asks_by_tool()
    assert len(probes) > 100 and len(asks) > 100  # positive control: the probes and the tools' asks are read
    assert near_copies(asks, probes) == []


def test_a_test_that_ranks_an_ask_of_its_app_as_a_persons_words_is_caught():
    """Positive control of the sweep below, on a test module of its own: what its tests rank as a person's words (a
    parametrized ``phrase``, with the tool of the ``name`` beside it, or a parametrized probe of layer 2) is caught when
    it is one of the app's asks, or one of its tool's asks but for one word; a phrase in the person's own words (an
    ``OWN_WORDS`` one, hub#1165: no ask, no probe) is not."""
    asks = {"x.menu.list": ("¿qué menús hay dados de alta?",), "x.menu.get": ("enséñame el menú del día",)}
    module = ModuleType("example")

    @pytest.mark.parametrize(
        ("name", "phrase"),
        [
            ("x.menu.list", "¿Qué menús hay dados de alta?"),  # its own ask
            ("x.menu.list", "¿qué menús hay dados de alta ahora?"),  # its own ask but for one word
            ("x.menu.list", "¿qué menús tenemos para hoy?"),  # in the person's own words
            pytest.param("x.menu.list", "Enséñame el menú del día", id="another-tools-ask"),  # an ask of the app
        ],
    )
    def test_reported(name, phrase): ...

    probe = {"id": "qa.x", "tool": "x.menu.get", "phrase": "enséñame el menú del jueves"}

    @pytest.mark.parametrize("probe", [probe])
    def test_every_probe(probe): ...

    @pytest.mark.parametrize(("language", "phrase"), [("es", "enséñame el menú del día"), ("es", "y el de mañana")])
    def test_without_a_tool(language, phrase): ...

    module.test_reported, module.test_every_probe, module.test_without_a_tool = (
        test_reported,
        test_every_probe,
        test_without_a_tool,
    )
    module.helper = test_reported  # not a test: what it would rank is no test's
    assert tautologies(module, asks) == [
        ("test_reported", "¿Qué menús hay dados de alta?", "¿qué menús hay dados de alta?"),
        ("test_reported", "¿qué menús hay dados de alta ahora?", "¿qué menús hay dados de alta?"),
        ("test_reported", "Enséñame el menú del día", "enséñame el menú del día"),
        ("test_every_probe", "enséñame el menú del jueves", "enséñame el menú del día"),
        ("test_without_a_tool", "enséñame el menú del día", "enséñame el menú del día"),
    ]


#: The test of each app's asks: what it ranks as a person's words is what the layer measures of the app.
APP_TESTS = sorted(Path(settings.BASE_DIR).glob("apps/*/tests/test_assistant_asks.py"))


def test_no_test_of_an_app_ranks_one_of_its_asks_as_a_persons_words():
    """The sweep above already brings every ask among the first ten, so a test of an app that ranks one of its asks (or
    one of its tool's asks but for one word) as what a person says measures nothing: green while the person's own
    words leave the tool out (hub#1126 and hub#1128, caught only by hand). The words a person says are the probes of
    layer 2 and phrases nobody wrote as asks, and every app's test ranks some (hub#1135)."""
    assert len(APP_TESTS) >= 10  # positive control: the tests of the apps are read
    found = {}
    for path in APP_TESTS:
        label = path.parts[-3]
        module = importlib.import_module(f"apps.{label}.tests.test_assistant_asks")
        assert ranked_phrases(module), label  # every app's test ranks a person's words, and they are read
        found[label] = tautologies(module, asks_by_tool(label))
    assert {label: said for label, said in found.items() if said} == {}


#: The requests of hub#1083's QA (``qa20261108.owner.es.base.*``), as the owner said them: each is offered its existing
#: operation (among the ``MAX_TOOLS`` a turn offers, so the model can choose it), without being one of its asks.
REPORTED = [
    ("base.file.read", "busca el documento Documentos QA/nota-qa.txt y dime su tamaño y tipo"),
    (
        "base.blueprint.import",
        "carga la plantilla de restaurante conservando lo que ya exista, sin traer personas ni información fiscal",
    ),
    ("base.app.enable", "quiero volver a tener Reservas disponible en el menú con todo lo que tenía"),
    ("base.device.mode_set", "convierte este ordenador en una caja compartida que pida PIN a cada empleado"),
    (
        "base.device.prune",
        "retira de una vez todos los equipos que nadie haya utilizado durante los últimos treinta días, menos este",
    ),
    (
        "base.device.remove",
        "he perdido el primer dispositivo de la lista; cierra su acceso y obliga a entrar de nuevo con una cuenta",
    ),
    # «pon al … el nombre» renames even with what it names in between.
    ("base.device.rename", "pon al dispositivo que estoy usando ahora el nombre «Ordenador de oficina QA»"),
    (
        "base.person.badge_remove",
        "la empleada de la demo ha perdido su tarjeta; desactiva esa placa sin quitarle el PIN ni la cuenta",
    ),
]


def test_the_hub_reads_a_placa_as_a_badge_and_an_employee_as_a_person():
    """``base.assistant.SYNONYMS``: «la placa» is the badge of ``base.person.badge_*`` and «la empleada» a
    ``base.person``, so a request in the words of the till's screens reaches those tools without their own asks."""
    concepts = shared.asked(["quita la placa de la empleada"], assistant.SYNONYMS).concepts
    assert any(shared.stem("badge") in concept for concept in concepts)
    assert any(shared.stem("person") in concept for concept in concepts)
    assert not any(shared.stem("badge") in concept for concept in shared.asked(["quita la placa de la empleada"]).concepts)


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    reported = [case.values if hasattr(case, "values") else case for case in REPORTED]
    assert [phrases.get(comparable(phrase)) for _, phrase in reported] == [
        f"qa20261108.owner.es.{name}" for name, _ in reported
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_platform_request_offers_its_existing_operation(context_of, name, phrase):
    assert place_of_no_ask(assistant.catalog(context_of(Membership.Role.OWNER, "es")), name, phrase) is not None


#: A phrase of some tools, each with the tool it asks for: reads and writes, both languages, and words only the Hub's
#: ``SYNONYMS`` read as it does («cuenta» is a table's check, «ticket» a sale).
SAMPLE = [
    ("es", "customer.customer.create", "apúntame a Ana con su teléfono 600 111 222"),
    ("en", "customer.consent.withdraw", "unsubscribe Marta from WhatsApp messages"),
    ("es", "sale.order.set_label", "ponle de nombre «Ana — terraza» a la cuenta"),
    ("es", "sale.sale.get", "¿qué llevaba el último ticket?"),
    ("en", "sale.order.get", "what's on table 4's check?"),
    ("es", "base.file.read", "¿de qué tipo es el documento del presupuesto y cuánto ocupa?"),
    ("es", "base.blueprint.import", "importa la plantilla de restaurante"),
    ("es", "base.app.enable", "recupera la app de fichajes que quité del menú"),
    ("es", "base.device.mode_set", "usa este portátil como caja de todo el equipo, con PIN"),
    ("es", "base.device.prune", "da de baja los equipos que no se han usado en el último mes"),
    ("es", "base.device.remove", "corta el acceso del móvil que se ha perdido"),
    ("es", "base.device.rename", "cambia el nombre de este dispositivo a «Caja 2»"),
    ("es", "base.person.badge_remove", "anula la tarjeta de Pedro, que se le ha perdido"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "name", "phrase"), SAMPLE)
def test_the_layer_ranks_each_phrase_where_a_turn_of_the_hub_offers_its_tool(context_of, language, name, phrase):
    """``misses`` is given the turn's own ranking (``base.assistant.RANKING``): the place it gives a tool is the one
    the turn (``base.assistant.relevant``) offers it at, so a turn that ranks otherwise fails here."""
    tools = assistant.catalog(context_of(Membership.Role.OWNER, language))
    assert phrase in shared.asks_of(tools[name])[language]  # positive control: the phrase is one of its asks
    turn = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in turn  # offered by the turn, so its place is known
    tool = shared.tool_name(name)
    # Every ask whose tool is not first in the turn is a miss with ``top=1``: its place, as the layer computes it.
    places = {
        miss.ask: miss.position for miss in misses(tools, language=language, top=1, **assistant.RANKING)
        if miss.tool_name == tool
    }
    # With what is always at hand in front, none of these is first: the layer reports each one's place.
    assert places[phrase] == turn.index(name) + 1


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


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_how_many_asks_of_each_listed_app_reach_their_tool_without_their_own_words_is_reported(context_of):
    """Counting its own phrase, every ask reaches its tool (the sweep above); without it (``own_asks=False``: the tool
    keeps its other asks and its description) is how a phrase nobody wrote yet would fare. Reported per listed app and
    language over the owner's catalogue (the largest), never failed: what each app's asks generalize to."""
    reached: dict[str, list[str]] = {label: [] for label in LISTED}
    for language in LANGUAGES:
        tools = assistant.catalog(context_of(Membership.Role.OWNER, language))
        reaches = report(tools, language, TOP, **assistant.RANKING)
        for label, said in reached.items():
            mine = [reach for reach in reaches if of_app(reach.tool_name, label)]
            asks = sum(len(shared.asks_of(op).get(language, ())) for op in tools.values() if op.app_label == label)
            assert sum(len(reach.asks) for reach in mine) == asks > 0  # every ask of the app is measured
            said.append(f"{language} {sum(reach.unseen_within for reach in mine)}/{asks}")
    lines = "; ".join(f"{label} {', '.join(said)}" for label, said in reached.items())
    warnings.warn(
        AsksReach(f"Asks that bring their tool among the first {TOP} without their own words: {lines}"), stacklevel=1
    )

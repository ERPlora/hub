"""Layer 1 of the assistant's QA (docs plan 2026-10-31, the assistant's knowledge and QA, §1.4): deterministic, with no
model and no network, in every pull request.

Every tool of an app listed in ``LIVE_ASSISTANT_ASKS_REQUIRED`` says what a person types to ask for it (its ``asks``,
``live.E020``), and each of those phrases, ranked exactly as a chat turn ranks (``base.assistant.RANKING``: the same
``ALWAYS`` first, the same ``APP_WORDS``, the Hub's own ``SYNONYMS`` and ``HOWTO``), brings its tool among the first ten
offered, against the real catalogue of each role of the Hub (``base.assistant.catalog`` of a member of business ``a``,
which has every module on: the largest catalogue a role can have). What a role may not run is not in its catalogue at
all. An app joins the list in the same pull request that completes its asks, and stays in it while any of its tools
says one; the ones still missing are reported per app (``AsksBacklog``), never failed. How many asks of each listed
app reach their tool without their own words (``own_asks=False``: how a person's new phrase would) is reported too
(``AsksReach``), never failed.
"""

import dataclasses
import json
import re
import unicodedata
import warnings
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

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
    """The tools of the apps not yet listed that say no asks, per app: the backlog of the fleet, never a failure."""


class AsksReach(UserWarning):
    """How many asks of each listed app bring their tool among the first ten without their own words, per language: how
    a person's new phrase would fare (``own_asks=False``), information and never a failure."""


@pytest.fixture
def context_of(make_user):
    users = {}

    def of(role: str, language: str) -> OperationContext:
        if role not in users:  # one person per role, whatever the language they ask in
            users[role] = make_user(f"qa-{role}", host=A.key, role=role)
        user = users[role]
        return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language=language)

    return of


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


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def offered_place(tools: dict[str, Operation], name: str, phrase: str, language: str = "es") -> int | None:
    """The place a turn offers ``name`` at for ``phrase`` (1 is first), ``None`` when it is not offered at all."""
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    return offered.index(name) + 1 if name in offered else None


def place_of_no_ask(tools: dict[str, Operation], name: str, phrase: str) -> int | None:
    """``offered_place`` of a tool the person holds for a ``phrase`` that is none of its asks in Spanish."""
    assert name in tools  # positive control: the person holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    return offered_place(tools, name, phrase)


def without_its_asks(tools: dict[str, Operation], name: str) -> dict[str, Operation]:
    """``tools`` with ``name`` saying no asks: how a turn ranks it by its name, its description and the groups alone."""
    op = tools[name]
    return {**tools, name: dataclasses.replace(op, ai={key: value for key, value in op.ai.items() if key != "asks"})}


def assert_reported_are_owner_probes(reported: Iterable[tuple[str, str]]) -> None:
    """Each ``(tool, phrase)`` an app's test reports is, word for word, the owner's Spanish probe of layer 2 of that
    tool (``owner.es.<tool>``): the phrases are the QA's, never written to fit."""
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in reported] == [f"owner.es.{name}" for name, _ in reported]


def assert_reached_by_its_asks(tools: dict[str, Operation], name: str, phrase: str) -> None:
    """A request in the person's own words (``OWN_WORDS`` of an app's test: neither an ask nor a probe) brings ``name``
    among the first ``TOP`` by its asks, and without them it does not: asks that stop reading as people speak fail."""
    assert comparable(phrase) not in probe_phrases()
    assert comparable(phrase) not in {comparable(ask) for asks in shared.asks_of(tools[name]).values() for ask in asks}
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= TOP, place
    before = without_its_asks(tools, name)
    assert not shared.asks_of(before[name])  # positive control: the tool is ranked without its asks
    unasked = offered_place(before, name, phrase)
    assert unasked is None or unasked > TOP, unasked


def test_no_ask_copies_a_qa_probe_or_names_a_qa_record():
    """The probes measure that the selection generalises (docs plan 2026-10-31 §1.5): a probe written into its tool's
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
    # «pon al … el nombre» renames even with what it names in between (ERPlora/live#47): 43rd of 40 before, now 4th.
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
    tools = assistant.catalog(context_of(Membership.Role.OWNER, "es"))
    assert name in tools
    assert phrase not in shared.asks_of(tools[name])["es"]
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered


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

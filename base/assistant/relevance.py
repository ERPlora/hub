"""What a turn of the Hub's assistant offers: the few tools of what was asked, best first (``relevant``), ranked by the
platform's words and each app's own (``synonyms``), with ``ALWAYS`` first.
"""

from collections.abc import Collection, Iterable
from types import MappingProxyType

from django.core import checks
from live import assistant as shared
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import Operation

#: The search in ERPlora's documentation (saas ASSISTANT-F28): how ERPlora works is answered from it, never from memory.
DOCS_SEARCH = "base.docs.search"
#: Always offered when the person may read them: the checklist, the business's own data and the documentation (a
#: how-to question, «¿cómo abro la caja?», shares no word with its tool).
ALWAYS = ("base.setup.status", "base.business.get", DOCS_SEARCH)
#: How a person names each app in a turn: its id, its name and its menu (``live.assistant.app_words``). The QA of the
#: assistant ranks with it too (``base/tests/test_assistant_asks.py``).
APP_WORDS = shared.app_words
#: What a word of the platform means in the Hub and nowhere else (``live.assistant`` keeps what it means in any
#: business): a «placa» is a person's badge (``base.person.badge_*``) and an «empleado» or «empleada» a ``base.person``.
#: What an app's own words mean the app says itself, in its ``LiveAppConfig`` (``SYNONYMS_ATTRIBUTE``), never here; so
#: does base for the words built from the apps' names («quita Tareas del menú»: ``base.apps.BaseConfig``).
SYNONYMS = (
    ("placa", "badge"),
    ("empleado", "empleada", "employee", "person"),
)
#: The attribute of an app's ``LiveAppConfig`` that says what its own words mean, in groups as ``SYNONYMS``'s: a word of
#: a group asks for all of them, and a phrase with spaces names its group without lending its stems to other words
#: (``assistant_synonyms = (("tarea", "tareas", "task", "tasks"),)``). ``base.E018`` checks them.
SYNONYMS_ATTRIBUTE = "assistant_synonyms"


def _synonym_problems(config: LiveAppConfig) -> list[str]:
    """What is wrong with the words ``config`` declares (none declared: nothing)."""
    declared = getattr(config, SYNONYMS_ATTRIBUTE, ())
    said = f"{config.label}.{SYNONYMS_ATTRIBUTE}"
    if not isinstance(declared, list | tuple) or not all(isinstance(group, list | tuple) for group in declared):
        return [f"{said} is not a list of groups of words."]
    return [
        f"{said} has {list(group)!r}, not a group of two words or more."
        for group in declared
        if len(group) < 2 or not all(isinstance(word, str) and word.strip() for word in group)
    ]


def _counts(config: LiveAppConfig, offered: Collection[str] | None) -> bool:
    """Whether ``config``'s words count in a turn that may offer the tools of the apps ``offered`` (``None``: any). A
    listed app's count in every turn, because a word one app teaches also names what others share (a «bloqueo» is a
    reservation's blocked date too). An app out of the store (``listed = False``, never shown to a customer) counts
    only where its tools are: elsewhere its words would only bring other apps' tools first. What ``base.E018`` refuses
    never counts."""
    return (offered is None or config.listed or config.label in offered) and not _synonym_problems(config)


def synonyms(offered: Collection[str] | None = None) -> tuple[tuple[str, ...], ...]:
    """The Hub's words: the platform's (``SYNONYMS``) and then, in the order of the apps, the groups each app says
    (``SYNONYMS_ATTRIBUTE``) that count in a turn offering the tools of the apps ``offered`` (``_counts``; ``None``:
    every app's). A word two groups say names both (``live.assistant`` joins every group of a stem), whichever app says
    it first: the order changes nothing."""
    return (
        *SYNONYMS,
        *(
            tuple(group)
            for config in all_live_app_configs()
            if _counts(config, offered)
            for group in getattr(config, SYNONYMS_ATTRIBUTE, ())
        ),
    )


@checks.register("base")
def check_synonyms(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E018``: an app says what its words mean (``SYNONYMS_ATTRIBUTE``) as groups of two words or more, each a
    text: one word alone means nothing more, and a group written bare would be read as its letters."""
    return [
        checks.Error(
            problem,
            hint=f'Declare {SYNONYMS_ATTRIBUTE} = (("<word>", "<word>", …), …) on the app\'s LiveAppConfig.',
            obj=config,
            id="base.E018",
        )
        for config in all_live_app_configs()
        for problem in _synonym_problems(config)
    ]


#: The help a how-to question asks for (``live.assistant.HOWTO_POINTS``): it ranks by being one, not only by ``ALWAYS``.
HOWTO = (DOCS_SEARCH,)


def ranking(tools: dict[str, Operation]) -> MappingProxyType:
    """How a turn ranks ``tools`` (``relevant``), and the assistant's QA with it, word for word
    (``base/tests/test_assistant_asks.py``): one place, so the QA never ranks otherwise than the turn. The Hub's words
    are the ones that count where the apps of ``tools`` are (``synonyms``)."""
    offered = {op.app_label for op in tools.values()}
    return MappingProxyType({"always": ALWAYS, "app_words": APP_WORDS, "synonyms": synonyms(offered), "howto": HOWTO})


def relevant(tools: dict[str, Operation], texts: Iterable[str], language: str) -> list[Operation]:
    """The tools of what ``texts`` ask, best first, at most ``MAX_TOOLS`` (``live.assistant.relevant``), as ``ranking``
    says."""
    return shared.relevant(tools, texts, language, **ranking(tools))

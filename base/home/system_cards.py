"""The cards the apps put in System › «Usage and plan» (``system_cards``)."""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from django.core import checks
from live.context import OperationContext
from live.meta import all_live_app_configs, LiveAppConfig

#: Where an app declares its cards of System › «Usage and plan» (:func:`system_cards`).
SYSTEM_CARDS_ATTRIBUTE = "system_cards"
#: What a card declares: its ``key`` and its ``component``, and the ``permission`` it needs, if any.
SYSTEM_CARD_FIELDS = frozenset({"key", "component", "permission"})
#: A component's name: a Vue file of the app's ``frontend/components/``, never a path.
COMPONENT_NAME = re.compile(r"[A-Z][A-Za-z0-9]*")


def system_cards(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[dict]:
    """The cards the apps of ``configs`` put in System › «Usage and plan» that the person of ``ctx`` may see, in the order
    each app declares them: ``{key, app, component}``, the component of the app's ``frontend/components/`` that paints
    the card and reads what it says through the app's own queries. An app declares them on its ``LiveAppConfig`` as
    :data:`SYSTEM_CARDS_ATTRIBUTE`: a list of ``{"key", "component"}`` and, for a card not everybody sees, its
    ``"permission"``."""
    cards = []
    for config in configs:
        for card in getattr(config, SYSTEM_CARDS_ATTRIBUTE, None) or ():
            if ctx.has(card.get("permission")):
                cards.append({"key": f"{config.label}.{card['key']}", "app": config.label, "component": card["component"]})
    return cards


def system_card_problems(config: LiveAppConfig, card: Any, seen: set[str]) -> list[str]:
    """What is wrong with one card of ``config``'s ``system_cards`` (``seen``: the keys of the cards before it)."""
    if not isinstance(card, Mapping):
        return [f"has {card!r}, not a mapping"]
    problems = [f"has a card with {field!r}, which a card does not take" for field in sorted(set(card) - SYSTEM_CARD_FIELDS)]
    key, component, permission = card.get("key"), card.get("component"), card.get("permission")
    if not key or not isinstance(key, str):
        problems.append("has a card without a key")
    elif key in seen:
        problems.append(f"has two cards {key!r}")
    else:
        seen.add(key)
    if not isinstance(component, str) or not COMPONENT_NAME.fullmatch(component):
        problems.append(f"has a card whose component {component!r} is no component's name")
    elif not (Path(config.path) / "frontend" / "components" / f"{component}.vue").is_file():
        problems.append(f"names {component!r}, which is no file of its frontend/components/")
    if permission is not None and permission not in config.permissions:
        problems.append(f"has a card needing {permission!r}, which is no permission of the app")
    return problems


def system_card_errors(configs: Iterable[LiveAppConfig]) -> list[checks.CheckMessage]:
    """``base.E015``: ``system_cards`` is a list of cards, each with a key of its own, the name of a component the app
    has and, if any, a permission of the app: a card that names no file would never mount, and nobody would know."""
    hint = (
        f'Declare {SYSTEM_CARDS_ATTRIBUTE} = [{{"key": "<card>", "component": "<Vue component of frontend/components/>"}}] '
        'on the LiveAppConfig of the module, with "permission": "<app>.<action>" for a card not everybody sees.'
    )
    errors = []
    for config in configs:
        declared = getattr(config, SYSTEM_CARDS_ATTRIBUTE, None)
        if declared is None:
            continue
        if not isinstance(declared, list | tuple):
            problems = [f"is {declared!r}, not a list of cards"]
        else:
            seen: set[str] = set()
            problems = [problem for card in declared for problem in system_card_problems(config, card, seen)]
        errors += [
            checks.Error(f"{config.label}'s {SYSTEM_CARDS_ATTRIBUTE} {problem}.", hint=hint, obj=config, id="base.E015")
            for problem in problems
        ]
    return errors


@checks.register("base")
def check_system_cards(app_configs: Any, **kwargs: Any) -> list[checks.CheckMessage]:
    return system_card_errors(all_live_app_configs())

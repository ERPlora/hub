"""Whose a record is: who the caller is to the apps that keep what people did (``me``), and the reads of a model whose
rows belong to someone (``Owned``), which give a person only theirs unless they may see everyone's (the market's «view
own / view all»: Square, Toast, Odoo). An app declares its own in ``apps/<app>/queries/ownership.py``, and
``tests/test_guardrails_ownership.py`` keeps its reads going through that declaration."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.db.models import Model, Q, QuerySet
from live.context import OperationContext
from live.meta import all_live_app_configs

from base.api_keys import KeyCaller
from base.apps_on import active_apps
from base.only_theirs import only_theirs
from base.permissions import is_a_person
from base.sensitive import VIEW_BUSINESS_TOTALS


#: Every «see everyone's» permission an ``Owned`` names: of them, an API key holds those its maker holds (BASE-F125).
_SEE_ALL: set[str] = set()


@dataclass(frozen=True)
class Me:
    """A person as the apps record them: ``username`` is what a record keeps as who did it (a sale's «charged by»), and
    ``records`` are their own records in the apps that keep people (their staff record), as each app answers it."""

    username: str
    records: frozenset[UUID]


def me(ctx: OperationContext) -> Me | None:
    """The caller as a person; ``None`` for one that is not (an API key, an automation, the platform): at the counter
    an API key stays on the customer's side."""
    if not is_a_person(ctx.actor):
        return None
    return _person(ctx, ctx.actor.get_username())


def _person(ctx: OperationContext, username: str) -> Me:
    """The person known as ``username``, their records asked to every app that is on and keeps people
    (``own_records`` on its ``LiveAppConfig``)."""
    on = active_apps(ctx.scope)
    records: set[UUID] = set()
    for config in all_live_app_configs():
        ask = getattr(config, "own_records", None)
        if ask is not None and config.label in on:
            records |= ask(username)
    return Me(username=username, records=frozenset(records))


def _reads_as(ctx: OperationContext) -> str | None:
    """Whose own the caller reads: a person, theirs; an API key, its maker's, as a key never sees more than whoever
    made it; ``None`` for a caller with no one behind (an automation, the platform, a key made before its maker was
    recorded), which reaches what its permission opens."""
    if is_a_person(ctx.actor):
        return ctx.actor.get_username()
    if isinstance(ctx.actor, KeyCaller) and ctx.actor.owner:
        return ctx.actor.owner
    return None


def see_all_permissions() -> frozenset[str]:
    """The «see everyone's» permissions of every declaration (``Owned.all_permission``)."""
    return frozenset(_SEE_ALL)


@dataclass(frozen=True)
class Owned:
    """The rows of ``model`` a caller reaches: all of them with ``all_permission``, else those ``mine`` says are the
    person's; an API key's, its maker's. A caller with no one behind has none of its own, so what its permission opens
    is every row."""

    model: type[Model]
    all_permission: str
    mine: Callable[[Me], Q]

    def __post_init__(self) -> None:
        _SEE_ALL.add(self.all_permission)

    def sees_all(self, ctx: OperationContext) -> bool:
        return ctx.has(self.all_permission) or _reads_as(ctx) is None

    def visible(self, ctx: OperationContext) -> QuerySet:
        if self.sees_all(ctx):
            return self.model.objects.all()
        only_theirs()
        return self.theirs(_person(ctx, _reads_as(ctx)))

    def theirs(self, person: Me) -> QuerySet:
        """The rows that are ``person``'s, whatever the caller holds: what a model whose rows follow these reads them
        by (an invoice is whoever's its sale is)."""
        return self.model.objects.filter(self.mine(person))

    def counted(self, ctx: OperationContext) -> QuerySet:
        """The rows a caller's figures add up (a period's totals, a day's takings, the close by person): the whole
        business's only with ``base.view_business_totals`` besides the «see all» permission. A person without both
        counts their own, even if they may open everyone's rows one by one."""
        whose = _reads_as(ctx)
        if ctx.has(VIEW_BUSINESS_TOTALS) or whose is None:
            return self.visible(ctx)
        only_theirs()
        return self.theirs(_person(ctx, whose))

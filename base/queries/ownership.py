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

from base.apps_on import active_apps
from base.sensitive import VIEW_BUSINESS_TOTALS

from .people import is_a_person


@dataclass(frozen=True)
class Me:
    """A person as the apps record them: ``username`` is what a record keeps as who did it (a sale's «charged by»), and
    ``records`` are their own records in the apps that keep people (their staff record), as each app answers it."""

    username: str
    records: frozenset[UUID]


def me(ctx: OperationContext) -> Me | None:
    """The caller as a person; ``None`` for one that is not (an API key, an automation, the platform). Their records
    are asked to every app that is on and keeps people (``own_records`` on its ``LiveAppConfig``)."""
    if not is_a_person(ctx.actor):
        return None
    on = active_apps(ctx.scope)
    records: set[UUID] = set()
    for config in all_live_app_configs():
        ask = getattr(config, "own_records", None)
        if ask is not None and config.label in on:
            records |= ask(ctx)
    return Me(username=ctx.actor.get_username(), records=frozenset(records))


@dataclass(frozen=True)
class Owned:
    """The rows of ``model`` a caller reaches: all of them with ``all_permission``, else those ``mine`` says are the
    person's. A caller that is not a person has none of its own, so what its permission opens is every row."""

    model: type[Model]
    all_permission: str
    mine: Callable[[Me], Q]

    def sees_all(self, ctx: OperationContext) -> bool:
        return ctx.has(self.all_permission) or not is_a_person(ctx.actor)

    def visible(self, ctx: OperationContext) -> QuerySet:
        if self.sees_all(ctx):
            return self.model.objects.all()
        return self.theirs(me(ctx))

    def theirs(self, person: Me) -> QuerySet:
        """The rows that are ``person``'s, whatever the caller holds: what a model whose rows follow these reads them
        by (an invoice is whoever's its sale is)."""
        return self.model.objects.filter(self.mine(person))

    def counted(self, ctx: OperationContext) -> QuerySet:
        """The rows a caller's figures add up (a period's totals, a day's takings, the close by person): the whole
        business's only with ``base.view_business_totals`` besides the «see all» permission. A person without both
        counts their own, even if they may open everyone's rows one by one."""
        if ctx.has(VIEW_BUSINESS_TOTALS) or not is_a_person(ctx.actor):
            return self.visible(ctx)
        return self.model.objects.filter(self.mine(me(ctx)))

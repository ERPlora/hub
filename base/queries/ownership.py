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
        rows = self.model.objects.all()
        if self.sees_all(ctx):
            return rows
        return rows.filter(self.mine(me(ctx)))

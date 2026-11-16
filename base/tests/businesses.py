"""Business A and business B side by side, each in its own database, for base's tests that work in them."""

import asyncio
import contextvars

from django.db import connections
from live.models import OutboxEvent

from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.business import A, B


def in_each(read, hub_b):
    """``read(A)`` in business A, at work, and ``read(B)`` inside business B: each one answers in its own."""
    with use_hub(hub_b):
        of_b = read(B)
    return read(A), of_b


def inside(hub, call, *args, **kwargs):
    """``call(*args, **kwargs)`` inside ``hub``'s database."""
    with use_hub(hub):
        return call(*args, **kwargs)


def scopes_of(name: str) -> list[tuple[str, str]]:
    """The scope of every ``name`` event in the outbox of the business at work."""
    return sorted(OutboxEvent.objects.filter(name=name).values_list("scope_kind", "scope_key"))


def without_a_business(coro) -> asyncio.Task:
    """A task of ``coro`` that starts as a server's does: with nothing of the caller's context, no business entered."""
    return asyncio.create_task(coro, context=contextvars.Context())


class SchemaEditor:
    """What a migration's ``RunPython`` function reads from its schema editor: the connection of the business at work,
    inside the test's transaction."""

    @property
    def connection(self):
        return connections[current_alias()]

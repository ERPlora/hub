"""The tools of the Hub's assistant (``catalog``): the operations of the apps on in this business (``active_apps``: its
right and its switch) that this person may run, by their ``ai=`` (``live.assistant.is_tool``: an ``AI``; ``INTERNAL``,
a «Not an assistant tool»/«System only» dictionary or one on what only the platform runs never), never the
assistant's own nor what is never done from the chat (``NOT_FROM_CHAT``: emptying the business, a file to download). A
write a manager may approve is theirs too (``approvals``).
"""

from collections.abc import Collection

from live import assistant as shared
from live.context import OperationContext, Scope
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import Operation

from base import activation, approvals, entitlement

#: Never from the chat (the old hub's «destructive actions of the hub itself»): emptying the business; a file.
NOT_FROM_CHAT = frozenset({"base.hub.reset", "base.blueprint.export"})


def is_tool(op: Operation) -> bool:
    """Whether ``op`` is a tool of the Hub's assistant: its ``ai=`` says so (``live.assistant.is_tool``) and it is
    neither done never from the chat (``NOT_FROM_CHAT``) nor the assistant's own."""
    return shared.is_tool(op, not_from_chat=NOT_FROM_CHAT) and not op.name.startswith("base.assistant.")


def active_apps(scope: Scope) -> dict[str, LiveAppConfig]:
    """The apps on in ``scope``'s business: every app of ours but the paid ones it has no right to and the ones it
    turned off (``base.activation``)."""
    left_out = entitlement.blocked_apps(scope) | activation.off_apps(scope)
    return {config.label: config for config in all_live_app_configs() if config.label not in left_out}


def catalog(ctx: OperationContext, *, active_labels: Collection[str] | None = None) -> dict[str, Operation]:
    """The tools of ``ctx``'s person: by name, in name order, of the apps on in its business (``active_labels``, else
    ``active_apps``). A write a manager may approve is theirs too, as its button on the screen is: running
    it asks for the approval."""
    tools = shared.catalog(
        ctx,
        active_labels=active_apps(ctx.scope) if active_labels is None else active_labels,
        not_from_chat=NOT_FROM_CHAT,
        approvable=lambda op: approvals.label_of(op) is not None,
    )
    return {name: op for name, op in tools.items() if is_tool(op)}

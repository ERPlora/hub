"""The tools of the Hub's assistant (``catalog``): the operations of the apps on in this business (``active_apps``: its
right and its switch) that this person may run, by their ``ai=`` (``live.assistant.is_tool``: an ``AI``; ``INTERNAL``,
a «Not an assistant tool»/«System only» dictionary or one on what only the platform runs never), never the search of
the rest (``base.assistant.find_tools``) nor what is never done from the chat (``NOT_FROM_CHAT``: emptying the
business, a file to download). A write a manager may approve is theirs too (``approvals``), unless their role says no to
it. A tool runs for the model with ``run``.
"""

from collections.abc import Collection

from live import assistant as shared
from live.context import OperationContext, Scope
from live.errors import NotFound
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import Operation

from base import activation, approvals, entitlement
from base.business import DEFAULT_CURRENCY, business_zone, currency_decimals
from base.operations import business_currency
from base.permissions import refused_outright

from .relevance import FIND_TOOLS

#: Never from the chat (the old hub's «destructive actions of the hub itself»): emptying the business; a file.
NOT_FROM_CHAT = frozenset({"base.hub.reset", "base.blueprint.export"})


def is_tool(op: Operation) -> bool:
    """Whether ``op`` is a tool of the Hub's assistant: its ``ai=`` says so (``live.assistant.is_tool``) and it is
    neither done never from the chat (``NOT_FROM_CHAT``) nor the search of the rest, which every turn offers apart."""
    return shared.is_tool(op, not_from_chat=NOT_FROM_CHAT) and op.name != FIND_TOOLS


def active_apps(scope: Scope) -> dict[str, LiveAppConfig]:
    """The apps on in ``scope``'s business: every app of ours but the paid ones it has no right to and the ones it
    turned off (``base.activation``)."""
    left_out = entitlement.blocked_apps(scope) | activation.off_apps(scope)
    return {config.label: config for config in all_live_app_configs() if config.label not in left_out}


def catalog(ctx: OperationContext, *, active_labels: Collection[str] | None = None) -> dict[str, Operation]:
    """The tools of ``ctx``'s person: by name, in name order, of the apps on in its business (``active_labels``, else
    ``active_apps``). A write a manager may approve is theirs too, as its button on the screen is: running
    it asks for the approval; not one a role the business gave them says no to."""
    refused = refused_outright(ctx.actor, ctx.scope, approvals.approvable_permissions(all_live_app_configs()))
    tools = shared.catalog(
        ctx,
        active_labels=active_apps(ctx.scope) if active_labels is None else active_labels,
        not_from_chat=NOT_FROM_CHAT,
        approvable=lambda op: approvals.label_of(op) is not None and op.permission not in refused,
    )
    return {name: op for name, op in tools.items() if is_tool(op)}


def run(ctx: OperationContext, op: Operation, arguments: str) -> shared.ToolOutcome:
    """``op`` run for ``ctx`` with the model's ``arguments`` (``live.assistant.run_tool``), its result told as the screens
    write it: its hours on the business's clock and each amount in the currency of the record that names one, else in
    the business's, with its decimals."""
    try:
        business = business_currency(ctx.scope)
    except NotFound:
        business = DEFAULT_CURRENCY
    return shared.run_tool(ctx, op, arguments, zone=business_zone(), money=lambda named: _with_decimals(named or business))


def _with_decimals(currency: str) -> tuple[str, int]:
    return currency, currency_decimals(currency)

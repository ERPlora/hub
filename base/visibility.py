"""Whether something an app declares for the Home is for a person: its own permission and the data permissions its
figures need."""

from live.context import OperationContext
from live.meta import Widget
from live.operations import registry
from live.sensitive import marked_fields


def widget_open(ctx: OperationContext, widget: Widget) -> bool:
    """Whether ``ctx``'s person gets ``widget``: they hold its permission and every permission marked on the fields of
    its operation's answer that its ``map`` reads. Without that, its figure would reach them empty."""
    return ctx.has(widget.permission) and all(ctx.has(permission) for permission in figure_permissions(widget))


def figure_permissions(widget: Widget) -> frozenset[str]:
    """The permissions marked on the fields of the answer of ``widget``'s operation that its ``map`` reads, at any
    depth (a panel of rows reads the fields of its rows); none for a panel drawn by a component."""
    operation = registry.get(widget.operation) if widget.operation else None
    if operation is None:
        return frozenset()
    read = set(widget.map.values())
    return frozenset(mark.permission for mark in marked_fields(operation.output) if mark.name in read)

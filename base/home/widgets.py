"""The panels of the dashboard the modules declare (``widgets``)."""

from collections.abc import Iterable, Mapping
from typing import Any

from django.utils.functional import Promise
from live.context import OperationContext
from live.live_registry import live_registry
from live.meta import LiveAppConfig

from base import visibility


def translated(value: Any) -> Any:
    """``value`` with its lazy translations, at any depth of its dicts and lists, as text in the language active now.

    A panel's literal props (``options``) may carry them, as the text under a stat's figure; nothing else changes.
    """
    if isinstance(value, Promise):
        return str(value)
    if isinstance(value, Mapping):
        return {key: translated(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [translated(item) for item in value]
    return value


def widgets(ctx: OperationContext, configs: Iterable[LiveAppConfig], hub_vertical: str) -> list[dict]:
    """The panels the person of ``ctx`` may put on their dashboard."""
    panels = []
    for config in configs:
        for widget in config.widgets:
            if not visibility.widget_open(ctx, widget):
                continue
            if widget.verticals and hub_vertical not in widget.verticals:
                continue
            panels.append(
                {
                    "key": f"{config.label}.{widget.key}",
                    "app": config.label,
                    "title": str(widget.title),
                    "icon": widget.icon,
                    "category": str(widget.category or config.verbose_name),
                    "size": widget.size,
                    "default": widget.default,
                    "kind": widget.kind,
                    "operation": widget.operation,
                    "params": dict(widget.params),
                    "map": dict(widget.map),
                    "options": translated(widget.options),
                    "component": widget.component,
                    "refresh_on": list(widget.refresh_on),
                    "live": widget.operation is not None and live_registry.is_subscribable(widget.operation),
                }
            )
    return panels

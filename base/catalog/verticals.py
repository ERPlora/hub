"""Verticals: the ones the modules belong to, and each one's template apps."""

from collections.abc import Iterable

from base.catalog.app_registry import catalog_modules


def known_verticals(configs: Iterable | None = None) -> list[str]:
    """Every vertical some module belongs to, sorted: the ones ``/internal`` accepts."""
    return sorted(
        {
            vertical
            for config in catalog_modules(configs)
            for vertical in config.verticals
        }
    )


def template_apps(vertical: str, configs: Iterable | None = None) -> list[str]:
    """The template apps of ``vertical``: the modules of that vertical, closed by ``requires``.

    A module lists a vertical only when every hub of it turns the module on at sign-up (in doubt,
    out); raises ``ValueError`` for a vertical no module lists.
    """
    modules = {config.label: config for config in catalog_modules(configs)}
    pending = [
        label for label, config in modules.items() if vertical in config.verticals
    ]
    if not pending:
        raise ValueError(f"Unknown vertical {vertical!r}: no module lists it.")
    closed: set[str] = set()
    while pending:
        label = pending.pop()
        if label not in closed:
            closed.add(label)
            pending.extend(modules[label].requires)
    return sorted(closed)

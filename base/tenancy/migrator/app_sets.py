"""What a hub's database may hold, by this code: its migrations, every hub app, the platform's and the portable
ones, and a list of apps closed by what each requires."""

from collections.abc import Iterable
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db.migrations.loader import MigrationLoader

from base.tenancy import inventory


class UnknownApp(LookupError):
    """An app this code does not have."""

    code = "unknown_app"


class AppNotPortable(ValueError):
    """An app whose tables reference a model of control's database: no hub's database can hold them. None: the
    people of a business are its own (``base.HubUser``), and ``tests/test_guardrails.py`` «(h)» keeps it so."""

    code = "app_not_portable"


@dataclass(frozen=True)
class CodeMigrations:
    """This code's migrations: every app's leaf and every node of the graph."""

    leaves: dict[str, str]
    nodes: frozenset[tuple[str, str]]


def code_migrations() -> CodeMigrations:
    """This code's migration graph: ``{app label: its leaf}`` and every ``(app label, migration)``."""
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    return CodeMigrations(leaves=dict(graph.leaf_nodes()), nodes=frozenset(graph.nodes))


def hub_apps() -> frozenset[str]:
    """Every app whose tables live in a hub's database: the platform's and every module of ``apps/``."""
    return frozenset(
        config.label
        for config in django_apps.get_app_configs()
        if config.name.startswith(inventory.HUB_MODULES_PACKAGE)
        or inventory.APP_CLASSES.get(config.label) == inventory.HUB
    )


def platform_apps() -> tuple[str, ...]:
    """What every hub's database has, whatever its apps: the apps that are a hub's whole (``base``, ``live``)."""
    installed = {config.label for config in django_apps.get_app_configs()}
    return tuple(
        sorted(label for label, kind in inventory.APP_CLASSES.items() if kind == inventory.HUB and label in installed)
    )


def _hub_classes(model) -> bool:
    return inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)


def portable_apps() -> tuple[str, ...]:
    """The hub apps whose tables reference only a hub's own, and whose migrations need no other app's.

    Every hub app: staff, attendance, task and whatsapp_inbox hang a person from the business's own
    ``base.HubUser``, not from control's user. An app that linked a model of control's again (and what depends on it)
    would be left out of every template and refused by ``add=``; ``tests/test_guardrails.py`` «(h)» stops it first.
    """
    labels = hub_apps()
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    needs = {
        label: {node[0] for leaf in graph.leaf_nodes() if leaf[0] == label for node in graph.forwards_plan(leaf)}
        & labels
        for label in labels
    }
    blocked = {
        label
        for label in labels
        for model in django_apps.get_app_config(label).get_models(include_auto_created=True)
        if _hub_classes(model)
        for field_ in model._meta.get_fields()
        if field_.is_relation and field_.concrete and field_.related_model is not None
        and inventory.classify(field_.related_model) == inventory.CONTROL
    }
    while grown := {label for label in labels - blocked if needs[label] & blocked}:
        blocked |= grown
    return tuple(sorted(labels - blocked))


def _with_requires(labels: Iterable[str]) -> set[str]:
    """``labels`` and what they require, transitively (each module's ``requires``); refused if one is unknown or no
    hub's database can hold it yet."""
    known = hub_apps()
    wanted = set(labels)
    if unknown := sorted(wanted - known):
        raise UnknownApp(f"No hub app is called {', '.join(unknown)} in this code.")
    closed: set[str] = set()
    pending = list(wanted)
    while pending:
        label = pending.pop()
        if label not in closed:
            closed.add(label)
            pending.extend(getattr(django_apps.get_app_config(label), "requires", ()) or ())
    if blocked := sorted(closed - set(portable_apps())):
        raise AppNotPortable(
            f"{', '.join(blocked)} cannot be created in a hub's database: their tables reference a model of "
            "control's database (tests/test_guardrails.py, «(h)»)."
        )
    return closed

"""Spec 2026-10-11 «tablas al activar» §11 and §14.11: an app's tables are made alone, with what it ``requires``, on
the platform's template (S3: the first time a hub turns it on). That holds only while every link and every migration
dependency of a module goes to the platform (``base``, ``live``) or to a module of its ``requires``, closed
transitively; a cycle in ``requires`` is ``live.E005`` (``packages/live/tests/test_checks.py``).

``base/tests/test_worker_activations.py`` makes each app alone on a real database; this checks every link statically,
so a new one outside ``requires`` fails here before any hub turns its app on.
"""

from collections.abc import Iterable, Mapping

from django.apps import apps as django_apps
from django.db.migrations.loader import MigrationLoader

from base import activation
from base.tenancy import migrator


def requires_problems(
    graph: Mapping[str, Iterable[str]],
    platform: Iterable[str],
    migration_needs: Mapping[str, Iterable[str]],
    links: Mapping[str, Iterable[tuple[str, str]]],
) -> list[str]:
    """What breaks «only towards a declared ``requires``»: a migration dependency or a link (``(field, app)``) of a
    module to a module outside its closure by ``requires``."""
    problems = []
    for label in graph:
        allowed = {label} | activation.needs([label], graph) | set(platform)
        for needed in sorted(set(migration_needs.get(label, ())) - allowed):
            problems.append(f"{label}: its migrations depend on {needed}, not in its requires")
        for field, target in sorted(links.get(label, ())):
            if target in graph and target not in allowed:
                problems.append(f"{label}: {field} links to {target}, not in its requires")
    return problems


def test_the_check_sees_a_link_and_a_migration_outside_requires():
    graph = {"sale": ("tax",), "tax": (), "task": ()}
    assert requires_problems(graph, ["base"], {"sale": ["tax", "base"]}, {"sale": [("Sale.tax", "tax")]}) == []
    assert requires_problems(graph, ["base"], {"sale": ["task"]}, {"tax": [("Rule.sale", "sale")]}) == [
        "sale: its migrations depend on task, not in its requires",
        "tax: Rule.sale links to sale, not in its requires",
    ]


def test_every_module_links_and_migrates_only_towards_its_requires_and_the_platform():
    graph = activation.module_graph()
    hub = migrator.hub_apps()
    loaded = MigrationLoader(None, ignore_no_migrations=True).graph
    migration_needs = {
        label: {node[0] for leaf in loaded.leaf_nodes() if leaf[0] == label for node in loaded.forwards_plan(leaf)}
        & hub
        for label in graph
    }
    links = {
        label: {
            (f"{model.__name__}.{field.name}", field.related_model._meta.app_label)
            for model in django_apps.get_app_config(label).get_models(include_auto_created=True)
            for field in model._meta.get_fields()
            if field.is_relation and field.concrete and field.related_model is not None
        }
        for label in graph
    }

    assert requires_problems(graph, migrator.platform_apps(), migration_needs, links) == []

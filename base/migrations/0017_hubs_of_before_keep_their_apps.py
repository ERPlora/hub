# Round 2026-10-27 (PLAN-HUB §9): a hub is born with every app off; the business turns on what it uses (Apps, or a
# blueprint, which turns its apps on and then loads). Until now a hub without any row of ``AppActivation`` had every
# app on, its roots chosen (the baseline of ``base.activation`` before this round). This writes that down for every hub
# of the registry that has no row yet, so none of them loses an app when the baseline turns off: the businesses, the
# demos alive and the developer's local hubs. A hub that already changed its apps has rows and keeps them; a purged
# demo is never served again. It runs where the registry is, control's database, which phase 1's hubs share (S1–S4);
# on a hub's own database (its ``__ddl`` alias) it has nothing to do. ERPlora's own hub and the worker's scope have
# every app on by construction (``base.activation.is_platform``), rows or not.
#
# Reverting forgets the rows of every hub whose rows are still exactly every app on (back to «no row», which the
# baseline of before read as every app on); a hub that changed something since keeps its rows.

from django.db import migrations, router
from live.meta import module_configs


def _every_app_on() -> dict[str, tuple[str, bool]]:
    """Every module of the deployment on, its roots chosen: those no other module needs (``base.activation``'s
    ``every_on``, written out here so this migration never changes with that module)."""
    graph = {config.label: tuple(getattr(config, "requires", ()) or ()) for config in module_configs()}
    needed: set[str] = set()
    pending = [required for requires in graph.values() for required in requires]
    while pending:
        label = pending.pop()
        if label not in needed:
            needed.add(label)
            pending.extend(graph.get(label, ()))
    return {label: ("on", label not in needed) for label in graph}


def _hosts_of_before(apps, schema_editor) -> list[str] | None:
    """The slugs of the registry's hubs whose apps live in this database, or ``None`` where the registry is not."""
    Hub = apps.get_model("control", "Hub")
    AppActivation = apps.get_model("base", "AppActivation")
    alias = schema_editor.connection.alias
    if not (router.allow_migrate_model(alias, Hub) and router.allow_migrate_model(alias, AppActivation)):
        return None
    return list(
        Hub.objects.using(schema_editor.connection.alias)
        .filter(db_name="")
        .exclude(status="purged")
        .order_by("slug")
        .values_list("slug", flat=True)
    )


def write_every_app_on(apps, schema_editor):
    hosts = _hosts_of_before(apps, schema_editor)
    if not hosts:
        return
    AppActivation = apps.get_model("base", "AppActivation")
    rows = AppActivation.objects.using(schema_editor.connection.alias)
    with_rows = set(rows.filter(host__in=hosts).values_list("host", flat=True).distinct())
    every_on = _every_app_on()
    rows.bulk_create(
        [
            AppActivation(host=host, app=app, state=state, chosen=chosen)
            for host in hosts
            if host not in with_rows
            for app, (state, chosen) in every_on.items()
        ],
        batch_size=1000,
    )


def forget_every_app_on(apps, schema_editor):
    hosts = _hosts_of_before(apps, schema_editor)
    if not hosts:
        return
    AppActivation = apps.get_model("base", "AppActivation")
    rows = AppActivation.objects.using(schema_editor.connection.alias)
    every_on = _every_app_on()
    found: dict[str, dict[str, tuple[str, bool]]] = {}
    for host, app, state, chosen in rows.filter(host__in=hosts).values_list("host", "app", "state", "chosen"):
        found.setdefault(host, {})[app] = (state, chosen)
    untouched = [host for host, kept in found.items() if kept == every_on]
    if untouched:
        rows.filter(host__in=untouched).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0016_app_activation"),
        ("control", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(write_every_app_on, forget_every_app_on),
    ]

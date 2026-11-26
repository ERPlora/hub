# A template or a copy now turns its apps on as the business does in Apps: each one chosen. Before, only the apps no
# other app needed were chosen, and turning one of those off took the rest along (a salon lost its agenda turning
# online bookings off). The history does not say which apps a load found on and which it turned on, so every app a
# load's report names as found on or turned on, and still wanted on, becomes chosen: one that is chosen never goes off
# along with another, so none goes off by mistake. Taxes stays as it was: every business is born with it on, and the
# business's country keeps it on, so choosing it would only take a place of the plan's limit.
# Going back leaves them chosen: the code of before reads a chosen app as it always did, and which ones were chosen by
# hand is not written anywhere.

from django.db import migrations

BORN_ON = ("tax",)
#: What a load's report says of an app it found off, did not know or was told to leave out.
NOT_TURNED_ON = ("inactive", "unknown", "not_selected")
WANTED = ("on", "creating", "failed")


def _apps_loads_turned_on(reports) -> set[str]:
    found: set[str] = set()
    for report in reports:
        apps = report.get("apps") if isinstance(report, dict) else None
        for app in apps if isinstance(apps, list) else ():
            if isinstance(app, dict) and isinstance(app.get("id"), str) and app.get("status") not in NOT_TURNED_ON:
                found.add(app["id"])
    return found - set(BORN_ON)


def choose_what_loads_turned_on(apps, schema_editor):
    loads = apps.get_model("base", "ImportBatch").objects.using(schema_editor.connection.alias)
    loaded = _apps_loads_turned_on(loads.values_list("report", flat=True))
    if loaded:
        apps.get_model("base", "AppActivation").objects.using(schema_editor.connection.alias).filter(
            app__in=sorted(loaded), state__in=WANTED, chosen=False
        ).update(chosen=True)


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0032_approval_by_role"),
    ]

    operations = [
        migrations.RunPython(
            choose_what_loads_turned_on, migrations.RunPython.noop, hints={"model_name": "appactivation"}
        ),
    ]

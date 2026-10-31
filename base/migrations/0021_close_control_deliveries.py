# The deliveries of an event of no hub (control's outbox: the registry's and the demos' events) still pending when the
# relay stopped handing such events to any app (hub#471): their reaction has no hub to run in, so each would fail on
# every attempt, with its traceback, until given up. They are closed ``dead`` at once, saying why (``control_scope``).
# A hub's own deliveries (scope ``host``) and the ones already closed stay as they are. Reverting leaves them closed:
# reopening them would only make them fail again.

from django.db import migrations

#: The scope of a hub's events (``base.tenancy.context.HUB_SCOPE_KIND``), copied: a migration never imports app code.
HUB_SCOPE_KIND = "host"
WHY = "control_scope: an event of no hub; no app of a hub hears it (hub#471)."


def close_control_deliveries(apps, schema_editor):
    EventDelivery = apps.get_model("base", "EventDelivery")
    EventDelivery.objects.using(schema_editor.connection.alias).filter(status="pending").exclude(
        event__scope_kind=HUB_SCOPE_KIND
    ).update(status="dead", last_error=WHY)


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0020_hub_user'),
    ]

    operations = [
        migrations.RunPython(close_control_deliveries, migrations.RunPython.noop),
    ]

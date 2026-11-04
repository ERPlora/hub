"""What a session of a voucher is worth (SERVICE-F24), and the sessions delivered before it had a value: each takes its
share of what its voucher was paid, in the order they were spent, so the ones spent from now on share only what is left.
Their sales keep what they counted: a sale is never edited."""

from itertools import groupby
from operator import attrgetter

from django.db import migrations, models
from django.db.models import Sum


def value_delivered_sessions(apps, schema_editor):
    Grant = apps.get_model("service", "Grant")
    Redemption = apps.get_model("service", "Redemption")
    alias = schema_editor.connection.alias
    pending = (
        Redemption.objects.using(alias)
        .filter(status="consumed", value__isnull=True, grant__max_uses__isnull=False)
        .order_by("grant_id", "redeemed_at", "id")
    )
    valued = []
    for grant_id, sessions in groupby(pending, key=attrgetter("grant_id")):
        grant = Grant.objects.using(alias).get(pk=grant_id)
        adjusted = grant.adjustments.using(alias).aggregate(total=Sum("uses_delta"))["total"] or 0
        sessions_left = grant.max_uses + adjusted
        amount_left = grant.amount
        for session in sessions:
            divisor = max(sessions_left, 1)
            session.value = (2 * amount_left + divisor) // (2 * divisor)
            amount_left -= session.value
            sessions_left -= 1
            valued.append(session)
    Redemption.objects.using(alias).bulk_update(valued, ["value"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("service", "0003_service_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="redemption",
            name="value",
            field=models.PositiveBigIntegerField(blank=True, null=True, verbose_name="value"),
        ),
        migrations.RunPython(value_delivered_sessions, migrations.RunPython.noop),
    ]

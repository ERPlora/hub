"""What a session of a voucher is worth (SERVICE-F24). The sessions delivered before it had a value keep it empty: their
vouchers say no line, so they count for nobody, as they did, and a sale is never edited."""

from django.db import migrations, models


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
    ]

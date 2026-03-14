from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeconfig',
            name='business_hours_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Enable business hours to keep the system responsive during operating times',
            ),
        ),
        migrations.AddField(
            model_name='storeconfig',
            name='business_hours',
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text='Operating hours per weekday. Format: {"mon": {"open": "09:00", "close": "22:00"}, ...}.',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0023_control_outbox_pending_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='ui_scale',
            field=models.PositiveSmallIntegerField(
                choices=[(80, '80%'), (90, '90%'), (100, '100%'), (110, '110%'), (120, '120%')],
                db_default=100,
                default=100,
                verbose_name='interface scale',
            ),
        ),
    ]

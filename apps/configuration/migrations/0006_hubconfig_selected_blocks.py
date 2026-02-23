from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0005_add_country_code_to_hubconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='hubconfig',
            name='selected_blocks',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of selected block slugs (e.g., ["crm", "pos", "invoicing"])',
            ),
        ),
    ]

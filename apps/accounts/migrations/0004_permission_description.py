# Generated manually - add description field to Permission

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_populate_role_obj'),
    ]

    operations = [
        migrations.AddField(
            model_name='permission',
            name='description',
            field=models.TextField(blank=True, help_text='Detailed description of what this permission allows'),
        ),
    ]

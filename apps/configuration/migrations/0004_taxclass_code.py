from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0003_storeconfig_social_and_public_site'),
    ]

    operations = [
        migrations.AddField(
            model_name='taxclass',
            name='code',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Machine-readable code for blueprint mapping (e.g., general, reduced, super_reduced, exempt)',
                max_length=50,
                verbose_name='Code',
            ),
        ),
    ]

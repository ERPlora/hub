from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0003_add_show_modules_in_sidebar'),
    ]

    operations = [
        migrations.AddField(
            model_name='hubconfig',
            name='developer_mode',
            field=models.BooleanField(
                default=False,
                help_text='Enable developer mode to show module development tools and info',
            ),
        ),
    ]

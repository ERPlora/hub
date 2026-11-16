from django.db import migrations, models


class Migration(migrations.Migration):
    """Let new code omit the legacy business columns during the rolling deploy."""

    dependencies = [("whatsapp_inbox", "0010_hub_users")]

    operations = [
        migrations.AlterField(
            model_name="channel",
            name="host",
            field=models.CharField(
                default="",
                db_default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="host",
            ),
        ),
        migrations.AlterField(
            model_name="conversation",
            name="erase_host",
            field=models.CharField(
                blank=True,
                default="",
                db_default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="business that erased it",
            ),
        ),
        migrations.AlterField(
            model_name="message",
            name="host",
            field=models.CharField(
                blank=True,
                default="",
                db_default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="host",
            ),
        ),
        migrations.AlterField(
            model_name="template",
            name="host",
            field=models.CharField(
                default="",
                db_default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="host",
            ),
        ),
        migrations.AlterField(
            model_name="templatesample",
            name="host",
            field=models.CharField(
                default="",
                db_default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="host",
            ),
        ),
    ]

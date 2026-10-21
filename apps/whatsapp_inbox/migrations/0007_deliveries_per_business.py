from django.db import migrations, models


class Migration(migrations.Migration):
    """A message the Hub sends (``Message.host``) and a number it asks erplora.com to forget (``Conversation.erase_host``)
    keep the business that made them, so that the worker's ``delivery.resume`` (phase 1: one fixed scope) hands each
    over for that business. Expand only: the columns come empty; a row made before has no business recorded and is
    resumed as the worker's scope, as it was. Going back drops the two columns."""

    dependencies = [
        ("whatsapp_inbox", "0006_templates_per_business"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="erase_host",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="business that erased it",
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="host",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="host",
            ),
        ),
    ]

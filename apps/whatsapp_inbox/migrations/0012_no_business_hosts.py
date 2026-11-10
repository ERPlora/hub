from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    """Remove business separation from the state only; the columns and their data stay."""

    dependencies = [("whatsapp_inbox", "0011_host_defaults")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="channel",
                    name="whatsapp_inbox_channel_one_per_host",
                ),
                migrations.RemoveField(model_name="channel", name="host"),
                migrations.RemoveField(model_name="conversation", name="erase_host"),
                migrations.RemoveField(model_name="message", name="host"),
                migrations.RemoveConstraint(
                    model_name="template",
                    name="whatsapp_inbox_template_live_host_name_language_unique",
                ),
                migrations.RemoveField(model_name="template", name="host"),
                migrations.AddConstraint(
                    model_name="template",
                    constraint=models.UniqueConstraint(
                        fields=("name", "language"),
                        condition=Q(deleted_at__isnull=True),
                        name="whatsapp_inbox_template_live_host_name_language_unique",
                    ),
                ),
                migrations.RemoveField(model_name="templatesample", name="host"),
            ]
        )
    ]

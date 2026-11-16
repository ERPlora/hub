from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    """Each business keeps its rows in its own database (hub#1053): the business each row carried from the tables
    the businesses shared before leaves the models only. Its columns, their data and the two unique guards that name
    them stay in the database for the code of before, which still runs while the deploy migrates
    (``base/tests/test_migration_safety.py``): ``0011`` gave them an empty default, so the code no longer writes
    them, and the guards still keep one channel row and one live template per name and language. A later deploy
    drops them (hub#1132)."""

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

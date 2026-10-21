from django.db import migrations, models


def keep_one_live_template_per_name(apps, schema_editor):
    """Back to one copy shared by every business: of each live name and language, the newest-synced business's
    stays, the others go (Meta's list in the next photo brings back what Meta holds)."""
    Template = apps.get_model("whatsapp_inbox", "Template")
    live = Template.objects.using(schema_editor.connection.alias).filter(deleted_at__isnull=True)
    newest = live.order_by("name", "language", models.F("synced_at").desc(nulls_last=True), "-id").distinct(
        "name", "language"
    )
    live.exclude(pk__in=newest.values("pk")).delete()


class Migration(migrations.Migration):
    """Each business's templates are its own (``host``, as ``Channel`` since 0005). The copies made before belong to
    no business for sure: they stay with an empty ``host`` (no business lists, edits or sends them; the staff still
    sees them in the admin), and each business's next photo brings back what Meta holds for it."""

    dependencies = [
        ("whatsapp_inbox", "0005_channel_per_business"),
    ]

    # In this order so that it also goes back: the live copies are trimmed to one per name before the shared
    # constraint returns.
    operations = [
        migrations.AddField(
            model_name="template",
            name="host",
            field=models.CharField(
                default="",
                editable=False,
                help_text="First label of the host of the business, e.g. “a” for a.localhost.",
                max_length=63,
                verbose_name="host",
            ),
            preserve_default=False,
        ),
        migrations.RemoveConstraint(
            model_name="template",
            name="whatsapp_inbox_template_live_name_language_unique",
        ),
        migrations.RunPython(migrations.RunPython.noop, keep_one_live_template_per_name),
        migrations.AddConstraint(
            model_name="template",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("host", "name", "language"),
                name="whatsapp_inbox_template_live_host_name_language_unique",
            ),
        ),
    ]

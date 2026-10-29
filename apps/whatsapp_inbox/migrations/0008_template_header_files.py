import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

#: The headers with a file: the Hub now sends them (F33), asking for the file.
FILE_HEADERS = ("IMAGE", "VIDEO", "DOCUMENT")


def fill_file_headers(apps, schema_editor):
    """The templates with a file header the Hub fills now (``models.hub_handles`` as of this migration): the rest of
    their content is what it already filled."""
    from apps.whatsapp_inbox.models import hub_handles

    Template = apps.get_model("whatsapp_inbox", "Template")
    rows = Template.objects.using(schema_editor.connection.alias).filter(header_format__in=FILE_HEADERS, supported=False)
    for row in rows:
        if hub_handles(row.category, row.header_format, row.header, row.body, row.buttons):
            Template.objects.using(schema_editor.connection.alias).filter(pk=row.pk).update(supported=True)


def unfill_file_headers(apps, schema_editor):
    """Before this migration no file header was the Hub's to fill."""
    Template = apps.get_model("whatsapp_inbox", "Template")
    Template.objects.using(schema_editor.connection.alias).filter(header_format__in=FILE_HEADERS).update(supported=False)


class Migration(migrations.Migration):
    """The file of a template's header with a photo, a video or a document chosen in the Hub (WHATSAPP_INBOX-F29,
    F33): a table of its own, the template's link to it, and the message's link to the one it was sent with. Expand
    only: the table comes empty and the links null (a template made before has a text header or none, or a file
    header made in WhatsApp Manager, which keeps none). The templates with a file header the Hub now sends are marked
    so. Going back drops the links and the table, and marks them not sent from here again; the files in the store
    stay, named by their content."""

    dependencies = [
        ('whatsapp_inbox', '0007_deliveries_per_business'),
    ]

    operations = [
        migrations.CreateModel(
            name='TemplateSample',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ('host', models.CharField(editable=False, help_text='First label of the host of the business, e.g. “a” for a.localhost.', max_length=63, verbose_name='host')),
                ('header_format', models.CharField(choices=[('IMAGE', 'Image'), ('VIDEO', 'Video'), ('DOCUMENT', 'Document')], max_length=10, verbose_name='header type')),
                ('key', models.CharField(editable=False, max_length=255, verbose_name='file in the store')),
                ('sha256', models.CharField(editable=False, max_length=64, verbose_name='sha256')),
                ('content_type', models.CharField(max_length=64, verbose_name='type')),
                ('size', models.PositiveBigIntegerField(verbose_name='size in bytes')),
                ('name', models.CharField(max_length=255, verbose_name='name')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created at')),
            ],
            options={
                'verbose_name': 'template header file',
                'verbose_name_plural': 'template header files',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddField(
            model_name='template',
            name='header_sample',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='whatsapp_inbox.templatesample', verbose_name='header file'),
        ),
        migrations.AddField(
            model_name='message',
            name='header_sample',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='whatsapp_inbox.templatesample', verbose_name='header file'),
        ),
        migrations.RunPython(fill_file_headers, unfill_file_headers),
    ]

# Kitchen used to queue its orders even where no active printer prints their function (a kitchen that cooks from its
# screen): they waited for nobody, rang the bell's «Nothing is printing» and would all come out at once the day a
# printer of that function was added. Each one still waiting is cancelled as the queue's «Cancel» does, its paper let
# go. Backwards, nothing to restore: those orders were cooked from the screen.

from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    printer = apps.get_model("printing", "Printer")
    job = apps.get_model("printing", "PrintJob")
    printed = printer.objects.using(schema_editor.connection.alias).filter(is_active=True).values("usage")
    waiting = job.objects.using(schema_editor.connection.alias).filter(
        status="pending", printer__isnull=True, source_app="kitchen"
    )
    waiting.exclude(usage__in=printed).update(
        status="cancelled", leased_until=None, cancelled_at=timezone.now(), document={}, html=""
    )


def backwards(apps, schema_editor):
    """Nothing to restore: those orders were cooked from the screen, and their paper is gone."""


class Migration(migrations.Migration):
    dependencies = [("printing", "0004_printjob_document_type_labels")]
    operations = [migrations.RunPython(forwards, backwards)]

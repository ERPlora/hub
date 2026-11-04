# An appointment saved before hub#636 ends its real minutes after its start.
# Before it, the end was the start plus the duration on the business's wall clock, so a booking over the change of
# time was saved an hour longer (October) or shorter (March) than booked (``engine.ends_at`` counts real time since).
# Every row whose end is not its start plus its minutes of real time (Postgres subtracts timestamps in real time) is
# written that end; the rest are not touched (``updated_at`` included). Backwards nothing changes: the wrong end is
# not worth keeping, and every reader accepts the right one.

from django.db import migrations

SQL = """
UPDATE appointment_appointment
   SET "end" = start + make_interval(mins => duration_minutes)
 WHERE "end" <> start + make_interval(mins => duration_minutes)
"""


def forwards(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(SQL)


class Migration(migrations.Migration):
    dependencies = [("appointment", "0002_appointment_order_id")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]

"""The default week of the schedule app (SCHEDULE-F12): Monday to Friday 09:00–18:00, the weekend closed.

Planted the first time a hub creates the app's tables (and in every template that carries it), only on
an empty week: a business that has any weekday keeps its own. The week is the market's (Odoo, Google
Calendar, Microsoft Bookings, Business Central, Lightspeed Reservations; schedules#36 of the current
product), not the business's: it stays unconfirmed (the «default week» notice) until somebody saves a
day or confirms it. All seven days, the weekend as explicit closed days: a missing day answers
``no_hours``, «nothing configured», not «closed».

The reverse removes the week while it is still unconfirmed; a confirmed week is the business's and stays.
The data is frozen here on purpose (a migration never imports the app's code).
"""

import datetime as dt

from django.db import migrations

OPENING = dt.time(9)
CLOSING = dt.time(18)
WORKING_DAYS = range(5)
CLOSED_DAYS = (5, 6)


def plant(apps, schema_editor):
    WeekDay = apps.get_model("schedule", "WeekDay")
    WeekDayInterval = apps.get_model("schedule", "WeekDayInterval")
    if WeekDay.objects.using(schema_editor.connection.alias).exists():
        return
    for weekday in WORKING_DAYS:
        day = WeekDay.objects.using(schema_editor.connection.alias).create(weekday=weekday, is_closed=False)
        WeekDayInterval.objects.using(schema_editor.connection.alias).create(
            day=day, position=0, open_time=OPENING, close_time=CLOSING
        )
    for weekday in CLOSED_DAYS:
        WeekDay.objects.using(schema_editor.connection.alias).create(weekday=weekday, is_closed=True)


def unplant(apps, schema_editor):
    WeekDay = apps.get_model("schedule", "WeekDay")
    ScheduleSettings = apps.get_model("schedule", "ScheduleSettings")
    if ScheduleSettings.objects.using(schema_editor.connection.alias).filter(hours_confirmed=True).exists():
        return
    WeekDay.objects.using(schema_editor.connection.alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [("schedule", "0001_initial")]

    operations = [migrations.RunPython(plant, unplant)]

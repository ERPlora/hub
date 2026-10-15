"""Events of the schedule app (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

Their payloads carry ids and dates only, never a special day's name or a change's reason (free text
where a business may write people's names). The schedule app reacts to no event of another app.
"""

WEEK_UPDATED = "schedule.week.updated"
SPECIAL_DAY_CREATED = "schedule.special_day.created"
SPECIAL_DAY_UPDATED = "schedule.special_day.updated"
SPECIAL_DAY_DELETED = "schedule.special_day.deleted"
OVERRIDE_CREATED = "schedule.override.created"
OVERRIDE_UPDATED = "schedule.override.updated"
OVERRIDE_DELETED = "schedule.override.deleted"
SETTINGS_UPDATED = "schedule.settings.updated"

SPECIAL_DAY_ALL = [SPECIAL_DAY_CREATED, SPECIAL_DAY_UPDATED, SPECIAL_DAY_DELETED]
OVERRIDE_ALL = [OVERRIDE_CREATED, OVERRIDE_UPDATED, OVERRIDE_DELETED]
ALL = [WEEK_UPDATED, *SPECIAL_DAY_ALL, *OVERRIDE_ALL, SETTINGS_UPDATED]
#: Every event that changes when the business is open.
HOURS_ALL = [WEEK_UPDATED, *SPECIAL_DAY_ALL, *OVERRIDE_ALL]

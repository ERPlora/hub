"""Events of the staff app (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

Their payloads carry ids only, never a reason for leaving or for an absence (personal data; sick
leave is health data). The staff app reacts to no event of another app.
"""

MEMBER_CREATED = "staff.member.created"
MEMBER_UPDATED = "staff.member.updated"
MEMBER_DEACTIVATED = "staff.member.deactivated"
MEMBER_TERMINATED = "staff.member.terminated"
ROLE_CREATED = "staff.role.created"
ROLE_UPDATED = "staff.role.updated"
SCHEDULE_CREATED = "staff.schedule.created"
SCHEDULE_UPDATED = "staff.schedule.updated"
SCHEDULE_DELETED = "staff.schedule.deleted"
TIME_OFF_CREATED = "staff.time_off.created"
TIME_OFF_APPROVED = "staff.time_off.approved"
TIME_OFF_REJECTED = "staff.time_off.rejected"
TIME_OFF_CANCELLED = "staff.time_off.cancelled"
SETTINGS_UPDATED = "staff.settings.updated"

MEMBER_ALL = [MEMBER_CREATED, MEMBER_UPDATED, MEMBER_DEACTIVATED, MEMBER_TERMINATED]
ROLE_ALL = [ROLE_CREATED, ROLE_UPDATED]
SCHEDULE_ALL = [SCHEDULE_CREATED, SCHEDULE_UPDATED, SCHEDULE_DELETED]
TIME_OFF_ALL = [
    TIME_OFF_CREATED,
    TIME_OFF_APPROVED,
    TIME_OFF_REJECTED,
    TIME_OFF_CANCELLED,
]
ALL = [*MEMBER_ALL, *ROLE_ALL, *SCHEDULE_ALL, *TIME_OFF_ALL, SETTINGS_UPDATED]

"""The staff app: who works and attends, their role, weekly schedule, time off and pay."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav, Widget

from apps.staff.events import (
    MEMBER_ALL,
    MEMBER_TERMINATED,
    MEMBER_UPDATED,
    ROLE_ALL,
    TIME_OFF_ALL,
    TIME_OFF_APPROVED,
    TIME_OFF_CANCELLED,
)

#: What re-runs each panel's query (live.py): the Home follows the same figures Staff's screens read.
FIGURE_EVENTS = [*MEMBER_ALL, *TIME_OFF_ALL]
AWAY_TODAY_EVENTS = [TIME_OFF_APPROVED, TIME_OFF_CANCELLED, MEMBER_UPDATED, MEMBER_TERMINATED]
BY_ROLE_EVENTS = [*ROLE_ALL, *MEMBER_ALL]


class StaffConfig(LiveAppConfig):
    name = "apps.staff"
    label = "staff"
    kind = "app"
    verbose_name = _("Staff")
    icon = "ion:id-card-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your team: records, roles, weekly schedules, time off with approval and commission rates."
    )
    description = _(
        "Staff keeps who works in your business and when: each professional's record with their "
        "role, contact details, hourly rate and commission, whether they take bookings, and their "
        "weekly schedule with breaks. Employees ask for time off and a manager approves or rejects it; "
        "approved time off is taken out of their availability, and everyone sees who is away today. "
        "A record can be linked to the person's account, so they see their own record and requests."
    )
    # A hair salon books its professionals from sign-up; a restaurant may go without the app.
    verticals = ["hair_salon"]
    default_auto_field = "django.db.models.BigAutoField"
    # The old module's permissions (module.json), one by one, plus asking for one's own time off.
    permissions = [
        "staff.view",
        "staff.view_compensation",
        "staff.add_member",
        "staff.change_member",
        "staff.delete_member",
        "staff.view_time_off",
        "staff.view_time_off_detail",
        "staff.manage_time_off",
        "staff.manage_settings",
        "staff.request_time_off",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier
    # role is gone: its directory view is the employee's.
    role_permissions = {
        "hub_owner": ["staff.*"],
        "hub_admin": ["staff.*"],
        "hub_manager": [
            "staff.view",
            "staff.view_compensation",
            "staff.add_member",
            "staff.change_member",
            "staff.view_time_off",
            "staff.view_time_off_detail",
            "staff.manage_time_off",
            "staff.manage_settings",
            "staff.request_time_off",
        ],
        "hub_employee": ["staff.view", "staff.view_time_off", "staff.request_time_off"],
    }
    # The old module's four tabs.
    navigation = [
        Nav(
            id="staff",
            label=_("Staff"),
            icon="ion:people-outline",
            path="/staff/members",
        ),
        Nav(
            id="roles", label=_("Roles"), icon="ion:shield-outline", path="/staff/roles"
        ),
        Nav(
            id="time_off",
            label=_("Time Off"),
            icon="ion:calendar-outline",
            path="/staff/time-off",
        ),
        Nav(
            id="schedules",
            label=_("Schedules"),
            icon="ion:time-outline",
            path="/staff/schedules",
        ),
    ]
    # The Home's panels (PLAN-HUB round 2026-10-21): the old module's five `widgets` (it had no `setup` nor `bell`),
    # on the queries Staff's own figures read (STAFF-F20, STAFF-F23), in every business. A KPI says its name once, in
    # its title (gh:hub#1105). Registered icons only: the old airplane and hourglass are asked for in UI-REQUESTS.md.
    widgets = [
        Widget(
            key="headcount",
            title=_("Active staff"),
            icon="ion:people-outline",
            size="sm",
            permission="staff.view",
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="staff.member.stats",
            map={"value": "active"},
            options={"format": "number"},
        ),
        Widget(
            key="on_leave_today",
            title=_("On leave today"),
            icon="ion:log-out-outline",
            size="sm",
            permission="staff.view_time_off",
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="stat",
            operation="staff.member.stats",
            map={"value": "absent_today"},
            options={"format": "number"},
        ),
        Widget(
            key="pending_time_off",
            title=_("Pending time off"),
            icon="ion:time-outline",
            size="sm",
            permission="staff.view_time_off",
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="staff.member.stats",
            map={"value": "pending_time_off"},
            options={"format": "number"},
        ),
        # Whole days first, then by name, with the type in the reader's language under each name.
        Widget(
            key="time_off_today",
            title=_("Today's time off"),
            icon="ion:calendar-outline",
            size="md",
            permission="staff.view_time_off",
            default=True,
            refresh_on=AWAY_TODAY_EVENTS,
            kind="timeline",
            operation="staff.time_off.today",
            map={"title": "member_name", "description": "leave_type_label"},
        ),
        # The old panel's ten at most, the role with more active people first.
        Widget(
            key="by_role",
            title=_("Staff by role"),
            icon="ion:shield-outline",
            size="md",
            permission="staff.view",
            refresh_on=BY_ROLE_EVENTS,
            kind="bar-list",
            operation="staff.role.list",
            params={"sort": "-member_count", "limit": 10},
            map={"label": "name", "value": "member_count"},
            options={"valueFormat": "number"},
        ),
    ]

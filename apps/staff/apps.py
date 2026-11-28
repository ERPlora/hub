"""The staff app: who works and attends, their role, weekly schedule, time off and pay."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav, Widget

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
    blueprint_stays = {
        "Member": "people",
        "Schedule": "people",
        "ScheduleDay": "people",
        "TimeOff": "people",
        "StaffSettings": "settings",
    }
    kind = "app"
    verbose_name = _("Staff")
    icon = "ion:id-card-outline"
    category = Category.PEOPLE
    premium = False
    # The app store's texts, which register_apps writes to shared.app.
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). To «desactivar» names the deactivation
    # itself (staff.member.deactivate and every other *.deactivate), not only a switch off, and what one «pide» or
    # «solicita» for oneself, a «solicitud», is a request (staff.time_off.request). To «enganchar» a record to an account
    # is to link it (staff.account.list, staff.member.update).
    assistant_synonyms = (
        ("desactiva", "desactivar", "deactivate"),
        ("pido", "solicito", "solicitud", "request"),
        ("engancha", "vincula", "link"),
    )
    # The old module's permissions (module.json), one by one, plus asking for one's own time off.
    permissions = {
        "staff.view": _("View the team, roles, schedules, availability, figures and settings"),
        "staff.view_compensation": _("View pay rates, commissions and HR notes"),
        "staff.add_member": _("Add team members"),
        "staff.change_member": _("Edit team members"),
        "staff.delete_member": _("Deactivate team members and register leavers"),
        "staff.view_time_off": _("View time off, without its reason"),
        "staff.view_time_off_detail": _("View the reason and notes of any time off"),
        "staff.manage_time_off": _("Record, approve, reject and cancel anyone's time off"),
        "staff.manage_settings": _("Manage roles, schedules and settings"),
        "staff.request_time_off": _("Request their own time off"),
    }
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
    # The sections of its tab bar, each opening with its permission: Commissions to whoever reads the team
    # (each person their own line; the team's with the pay), Roles and Settings to whoever may save the settings.
    navigation = [
        Nav(
            id="staff",
            label=_("Staff"),
            icon="ion:people-outline",
            path="/staff/members",
            permission="staff.view",
        ),
        Nav(
            id="roles", label=_("Roles"), icon="ion:shield-outline", path="/staff/roles",
            permission="staff.manage_settings",
        ),
        Nav(
            id="time_off",
            label=_("Time Off"),
            icon="ion:calendar-outline",
            path="/staff/time-off",
            permission="staff.view_time_off",
        ),
        Nav(
            id="schedules",
            label=_("Schedules"),
            icon="ion:time-outline",
            path="/staff/schedules",
            permission="staff.view",
        ),
        Nav(
            id="commissions",
            label=_("Commissions"),
            icon="ion:wallet-outline",
            path="/staff/commissions",
            permission="staff.view",
        ),
        Nav("settings", _("Settings"), "ion:settings-outline", "/staff/settings", permission="staff.manage_settings"),
    ]
    help = Help(
        videos={"es": "7taPYc-k-qs", "en": "nJ9BqRfPEjk"},
        flow_videos={
            "STAFF-F01": {"es": ["Gk4r1B106fg"], "en": ["nwm7h2QLwqg"]},
            "STAFF-F02": {"es": ["Gk4r1B106fg"], "en": ["nwm7h2QLwqg"]},
            "STAFF-F03": {"es": ["LtnOnUQgr4A"], "en": ["HJOfAE_-p5c"]},
            "STAFF-F04": {"es": ["sLq3eX0EGo0"], "en": ["P--8qxE9jec"]},
            "STAFF-F06": {"es": ["Gk4r1B106fg"], "en": ["nwm7h2QLwqg"]},
            "STAFF-F08": {"es": ["wTNTqelgVUc"], "en": ["uAYP1JX9JFA"]},
            "STAFF-F17": {"es": ["0LsycLDgSbE"], "en": ["TZviOQ5zg_o"]},
            "STAFF-F18": {"es": ["0LsycLDgSbE"], "en": ["TZviOQ5zg_o"]},
            "STAFF-F19": {"es": ["0LsycLDgSbE"], "en": ["TZviOQ5zg_o"]},
            "STAFF-F24": {"es": ["I5v2868sR3w"], "en": ["XOdtwmIA5qk"]},
        },
    )
    # The Home's panels, on the queries Staff's own figures read (STAFF-F20, STAFF-F23), in every business. A KPI says
    # its name once, in its title. Registered icons only: the old airplane and hourglass are asked for in
    # UI-REQUESTS.md.
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
            title=_("Today’s time off"),
            icon="ion:calendar-outline",
            size="md",
            permission="staff.view_time_off",
            default=True,
            refresh_on=AWAY_TODAY_EVENTS,
            kind="timeline",
            operation="staff.time_off.today",
            map={"title": "member_name", "description": "leave_type_label"},
        ),
        # The old panel's ten at most, the role with more active people first, each bar in its role's colour (a role
        # without one keeps the panel's).
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
            map={"label": "name", "value": "member_count", "color": "color"},
            options={"valueFormat": "number"},
        ),
    ]

    def own_records(self, username: str) -> frozenset:
        """The live staff record of the person known as ``username``, what other apps count as theirs: the sales
        attributed to them (``base.queries.ownership``); none without one."""
        from apps.staff.queries.records import records_of  # the models are not loaded yet when this module is

        return records_of(username)

    def blueprint_datasets(self) -> list:
        """What of Staff travels in an export of the business (BASE-F35): its roles, never its people."""
        from apps.staff import blueprint  # base.blueprint loads the apps' models, not loaded yet when this module is

        return blueprint.DATASETS

"""The staff app: who works and attends, their role, weekly schedule, time off and pay."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


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

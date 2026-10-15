"""The attendance app: the legal working-day record (art. 34.9 ET) — clock in and out with one tap,
breaks, corrections with a mandatory reason and their trail, and the month in CSV (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, LiveAppConfig, Nav


class AttendanceConfig(LiveAppConfig):
    name = "apps.attendance"
    label = "attendance"
    kind = "app"
    verbose_name = _("Time clock")
    # `ion:time-outline` is the Schedules app's on the apps page; the fingerprint the market uses waits
    # in UI-REQUESTS.md.
    icon = "ion:log-in-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Clock in and out with one tap, breaks, corrections with a reason and the legal working-day record."
    )
    description = _(
        "Time clock is your business's working-day record: each person clocks in and out with one tap, "
        "with breaks in between; a manager sees the whole team and who is in right now, corrects a "
        "wrong day with a mandatory reason that stays in its history, and exports the month in CSV for "
        "the accountant or a labour inspection. Days are never deleted and every worker sees their own, "
        "as Spanish law requires (art. 34.9 ET), and a personal phone can be asked to be at the "
        "workplace to clock in."
    )
    # Every business with employees keeps the working-day record (art. 34.9 ET).
    verticals = ["hair_salon", "restaurant"]
    # A working day belongs to a staff record (staff.Member).
    requires = ["staff"]
    default_auto_field = "django.db.models.BigAutoField"
    # The old module's four permissions (module.json), plus clocking someone else (ATTENDANCE-F12).
    permissions = [
        "attendance.clock",
        "attendance.view_all",
        "attendance.correct",
        "attendance.clock_others",
        "attendance.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["attendance.*"],
        "hub_admin": ["attendance.*"],
        "hub_manager": ["attendance.*"],
        "hub_employee": ["attendance.clock"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. The old module's two entries with their old icons.
    navigation = [
        Nav(
            "clock",
            pgettext_lazy("attendance menu", "Clock in"),
            "ion:time-outline",
            "/attendance/clock",
        ),
        Nav(
            "records",
            pgettext_lazy("attendance menu", "Records"),
            "ion:list-outline",
            "/attendance/records",
        ),
    ]
    # ATTENDANCE-F05: the phase-2 worker runs it on every hub as the system (cron in UTC); clocking in
    # applies it to the person too, so a forgotten day never blocks the next one meanwhile.
    scheduled_tasks = [
        {
            "name": "review_stale",
            "operation": "attendance.record.review_stale",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]

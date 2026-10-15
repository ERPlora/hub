"""The schedule app: when the business is open — the usual week, special days and temporary changes.

The per-person hours (each professional's weekly schedule, time off and availability) are staff's: this
app knows nobody of the team and requires no other app (WORKBOOK «Referencia adoptada»).
"""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, LiveAppConfig, Nav


class ScheduleConfig(LiveAppConfig):
    name = "apps.schedule"
    label = "schedule"
    kind = "app"
    verbose_name = _("Schedules")
    icon = "ion:time-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your opening hours: the usual week, holidays and temporary changes like summer hours."
    )
    description = _(
        "Schedules keeps when your business is open: the usual week with split shifts, days open 24 hours "
        "or past midnight, special days such as holidays (closed, or with other hours, once or every year) "
        "and temporary changes for a few dates, like holidays or summer hours. It starts with a usual "
        "week you confirm in one tap, and the appointment book uses it to never take a booking while you "
        "are closed."
    )
    # A hair salon books inside its opening hours; a restaurant shows and keeps its own.
    verticals = ["hair_salon", "restaurant"]
    default_auto_field = "django.db.models.BigAutoField"
    # The old module's five permissions (module.json), renamed <app>.<action>.
    permissions = [
        "schedule.view",
        "schedule.add",
        "schedule.change",
        "schedule.delete",
        "schedule.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["schedule.*"],
        "hub_admin": ["schedule.*"],
        "hub_manager": ["schedule.*"],
        "hub_employee": ["schedule.view"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =`
    # as the module's own icon. The old `star-outline` of «Special days» is not registered in the shell
    # (UI-REQUESTS.md): `calendar-outline` stands in.
    navigation = [
        Nav("hours", pgettext_lazy("schedule section", "Hours"), "ion:time-outline", "/schedule/hours"),
        Nav(
            "special_days",
            _("Special days"),
            "ion:calendar-outline",
            "/schedule/special-days",
        ),
        Nav("settings", pgettext_lazy("schedule section", "Settings"), "ion:settings-outline", "/schedule/settings"),
    ]

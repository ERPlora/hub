"""The schedule app: when the business is open — the usual week, special days and temporary changes.

The per-person hours (each professional's weekly schedule, time off and availability) are staff's: this
app knows nobody of the team and requires no other app (WORKBOOK «Referencia adoptada»).
"""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, Help, LiveAppConfig, Nav, SetupCheck, SetupStep

from apps.schedule.events import WEEK_UPDATED


class ScheduleConfig(LiveAppConfig):
    name = "apps.schedule"
    label = "schedule"
    kind = "app"
    verbose_name = _("Schedules")
    icon = "ion:time-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    permissions = {
        "schedule.view": _("View the week, special days, changes and whether it is open"),
        "schedule.add": _("Add special days and temporary changes"),
        "schedule.change": _("Set and confirm the week, and correct special days and changes"),
        "schedule.delete": _("Delete special days and temporary changes"),
        "schedule.manage_settings": _("Change the settings"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["schedule.*"],
        "hub_admin": ["schedule.*"],
        "hub_manager": ["schedule.*"],
        "hub_employee": ["schedule.view"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =`
    # as the module's own icon. `star-outline` for «Special days» is not registered in the shell
    # (UI-REQUESTS.md): `calendar-outline` stands in.
    navigation = [
        Nav(
            "hours", pgettext_lazy("schedule section", "Hours"), "ion:time-outline", "/schedule/hours",
            permission="schedule.change",
        ),
        Nav(
            "special_days",
            _("Special days"),
            "ion:calendar-outline",
            "/schedule/special-days",
            permission="schedule.change",
        ),
        Nav(
            "settings", pgettext_lazy("schedule section", "Settings"), "ion:settings-outline", "/schedule/settings",
            permission="schedule.manage_settings",
        ),
    ]
    # The Home's step «Confirm your opening hours», order 101 and recommended, done once a person confirmed the
    # default week or saved a day of it (the settings' ``hours_confirmed``), for whoever changes the hours, leading to
    # the week. Refreshed on the only event that sets it. Its texts name no day or hour: they stay on the list once the
    # week is the business's own, and the assistant read the default week in them as the week the business has.
    setup = [
        SetupStep(
            key="hours",
            operation="schedule.settings.get",
            configured_when=[SetupCheck(field="hours_confirmed", truthy=True)],
            title=_("Confirm your opening hours"),
            description=_(
                "Check that the week's hours are your business's: if they are, confirm them in one tap; if not, edit "
                "the days that differ — bookings outside your opening hours are refused."
            ),
            icon="ion:time-outline",
            route="/schedule/hours",
            permission="schedule.change",
            order=101,
            required=False,
            refresh_on=[WEEK_UPDATED],
        )
    ]
    help = Help()

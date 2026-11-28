"""The attendance app: the legal working-day record (art. 34.9 ET) — clock in and out with one tap,
breaks, corrections with a mandatory reason and their trail, and the month in CSV (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, Help, LiveAppConfig, Nav, Widget

from apps.attendance.events import WHO_IS_IN


class AttendanceConfig(LiveAppConfig):
    name = "apps.attendance"
    label = "attendance"
    blueprint_stays = {
        "Record": "history",
        "Break": "history",
        "Correction": "history",
        "AttendanceSettings": "settings",
    }
    kind = "app"
    verbose_name = _("Time clock")
    # Not `ion:time-outline`: that is the Schedules app's icon on the apps page.
    icon = "ion:finger-print-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms): «mi salida» or «mi entrada»
    # is clocking (attendance.record.clock_*). Only after «mi»: «la salida de» or «su entrada» also says the drawer's
    # money, goods received or a place in the waiting list. «En pausa» is a break («pon a Javi en pausa»); «pausa»
    # alone also pauses a recipe or a series, and «descanso» is also a day off.
    assistant_synonyms = (
        ("clock", "mi salida", "mi entrada", "my departure", "my exit", "my arrival"),
        ("break", "en pausa"),
    )
    # Clocking someone else in or out (ATTENDANCE-F12) is a permission of its own.
    permissions = {
        "attendance.clock": _("Clock in and out, and see and export their own history"),
        "attendance.view_all": _("View the whole team's shifts and who is in"),
        "attendance.correct": _("Correct shifts"),
        "attendance.clock_others": _("Clock other people in and out, and their breaks"),
        "attendance.manage_settings": _("Change the settings"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["attendance.*"],
        "hub_admin": ["attendance.*"],
        "hub_manager": ["attendance.*"],
        "hub_employee": ["attendance.clock"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon.
    navigation = [
        Nav(
            "clock",
            pgettext_lazy("attendance menu", "Clock in"),
            "ion:time-outline",
            "/attendance/clock",
            permission="attendance.clock",
        ),
        Nav(
            "records",
            pgettext_lazy("attendance menu", "Records"),
            "ion:list-outline",
            "/attendance/records",
            permission="attendance.clock",
        ),
        Nav(
            "settings", _("Settings"), "ion:settings-outline", "/attendance/settings",
            permission="attendance.manage_settings",
        ),
    ]
    # The Home's panel «Clocked in now» (ATTENDANCE-F11), on the count of what Records lists, in every business.
    # A KPI says its name once, in its title.
    widgets = [
        Widget(
            key="clocked_in_now",
            title=_("Clocked in now"),
            icon="ion:time-outline",
            size="sm",
            permission="attendance.view_all",
            default=True,
            refresh_on=WHO_IS_IN,
            kind="kpi",
            operation="attendance.presence.count",
            map={"value": "count"},
            options={"format": "number"},
        )
    ]
    # ATTENDANCE-F05: the worker runs it as the system every quarter of an hour (cron in UTC); clocking in
    # applies it to the person too, so a forgotten day never blocks the next one.
    scheduled_tasks = [
        {
            "name": "review_stale",
            "operation": "attendance.record.review_stale",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]
    help = Help(
        videos={"es": "uOXeTh1ZSSE", "en": "bJRtG4HzBgM"},
        flow_videos={
            "ATTENDANCE-F01": {"es": ["d0mJ-eWWSs4"], "en": ["r7rMT_CeHdI"]},
            "ATTENDANCE-F02": {"es": ["-r7iRA_l84E"], "en": ["NqHXQAtrRXs"]},
            "ATTENDANCE-F06": {"es": ["7Iw3EckX5sk"], "en": ["vO7WaXRXYLI"]},
            "ATTENDANCE-F07": {"es": ["2AIG_S251qE"], "en": ["ISb1OnHEnUA"]},
            "ATTENDANCE-F10": {"es": ["2AIG_S251qE"], "en": ["ISb1OnHEnUA"]},
        },
    )

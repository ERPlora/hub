"""The cash register app: the drawer's cash by shifts — sessions with their opening float, the cash in and
out recorded by hand, the counts by notes and coins, and the close that compares the expected cash with
the counted one (WORKBOOK.md). The sale lines of a shift are read from sale, its requirement."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class CashRegisterConfig(LiveAppConfig):
    name = "apps.cash_register"
    label = "cash_register"
    kind = "app"
    verbose_name = _("Cash register")
    icon = "ion:cash-outline"
    category = Category.SALES
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Open and close the drawer by shifts, record cash in and out, count it and see the difference."
    )
    description = _(
        "Cash register keeps the drawer's cash by shifts. Open a session with the float in the drawer; the "
        "cash sales, voids and refunds of the till show up by themselves, and the cash brought in or taken out "
        "is recorded with its reason. Count the drawer by notes and coins and close the shift: the expected "
        "cash, the counted one and the difference stay for good, a closed shift never changes, a forgotten one "
        "closes itself at the end of the day, and the shift report prints as an X or a Z report."
    )
    verticals = ["hair_salon", "restaurant"]
    # The shift's sale lines are sale's own charges, voids and refunds (read from its models).
    requires = ["sale"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "cash_register.view_session",
        "cash_register.add_session",
        "cash_register.close_session",
        "cash_register.view_movement",
        "cash_register.add_movement",
        "cash_register.view_count",
        "cash_register.add_count",
        "cash_register.view_expected_totals",
        "cash_register.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier is
    # the employee: opens, records, counts and closes. The manager also sees a blind count's expected.
    role_permissions = {
        "hub_owner": ["cash_register.*"],
        "hub_admin": ["cash_register.*"],
        "hub_manager": [
            "cash_register.view_session",
            "cash_register.add_session",
            "cash_register.close_session",
            "cash_register.view_movement",
            "cash_register.add_movement",
            "cash_register.view_count",
            "cash_register.add_count",
            "cash_register.view_expected_totals",
        ],
        "hub_employee": [
            "cash_register.view_session",
            "cash_register.add_session",
            "cash_register.close_session",
            "cash_register.view_movement",
            "cash_register.add_movement",
            "cash_register.view_count",
            "cash_register.add_count",
        ],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only (packages/ui/src/shell/icons.ts).
    navigation = [
        Nav(
            "sessions",
            _("Cash register"),
            "ion:cash-outline",
            "/cash_register/sessions",
        ),
        Nav(
            "settings", _("Settings"), "ion:settings-outline", "/cash_register/settings"
        ),
    ]
    # The daily auto-close (CASH_REGISTER-F10): the phase-2 worker runs it on every hub as the system
    # (cron in UTC; the operation reads the business's own cut-off hour). Opening a session applies it
    # too, so a forgotten shift never blocks the next one meanwhile.
    scheduled_tasks = [
        {
            "name": "auto_close_sessions",
            "operation": "cash_register.session.auto_close",
            "cron": "*/5 * * * *",
            "catch_up": "collapse",
        }
    ]

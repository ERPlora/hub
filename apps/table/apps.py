"""The table app: the restaurant's floor plan — its zones, its tables and the checks seated at them
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class TableConfig(LiveAppConfig):
    name = "apps.table"
    label = "table"
    kind = "app"
    verbose_name = _("Tables")
    # Registered in the shell (ION_ICONS); the old `map-outline` waits in UI-REQUESTS.md.
    icon = "ion:grid-outline"
    category = Category.RESTAURANT
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your dining room: zones, tables on a live floor plan, and the checks seated at each table."
    )
    description = _(
        "Tables is the floor plan of your restaurant or bar. Draw the zones of the room and place the "
        "tables by dragging them, with their seats and their shape. During service the plan is live: "
        "each table says whether it is free, taken, reserved or out of service, how many guests sit "
        "there, for how long and who serves them. Seat a party and its check opens in the till; move "
        "it to another table, join two tables' checks or split one, and the table frees itself when "
        "the check is charged."
    )
    verticals = ["restaurant"]
    # The check of every table is an open check of Sales (its id, its status, its sales); its
    # customer is Customers' order link. Sales does not require Tables: it only knows titles.
    requires = ["sale", "customer"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "table.view_zone",
        "table.add_zone",
        "table.change_zone",
        "table.delete_zone",
        "table.view_table",
        "table.add_table",
        "table.change_table",
        "table.delete_table",
        "table.view_session",
        "table.add_session",
        "table.change_session",
        "table.transfer_session",
        "table.delete_session",
        "table.view_settings",
        "table.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier
    # (an employee who also charges) is the employee now.
    role_permissions = {
        "hub_owner": ["table.*"],
        "hub_admin": ["table.*"],
        "hub_manager": [
            "table.view_zone",
            "table.add_zone",
            "table.change_zone",
            "table.view_table",
            "table.add_table",
            "table.change_table",
            "table.view_session",
            "table.add_session",
            "table.change_session",
            "table.transfer_session",
            "table.view_settings",
        ],
        "hub_employee": [
            "table.view_zone",
            "table.view_table",
            "table.view_session",
            "table.add_session",
            "table.change_session",
            "table.transfer_session",
            "table.view_settings",
        ],
    }
    # TABLE-F29: the holds whose window passed are marked expired, every hour, by the worker as the
    # system (cron in UTC). Phase 1 sweeps the one database every hub shares; phase 2 runs it per hub,
    # each under ``use_hub``. Reading the plan already ignores them.
    scheduled_tasks = [
        {
            "name": "expire_table_holds",
            "operation": "table.hold.expire",
            "cron": "0 * * * *",
            "catch_up": "collapse",
        }
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only: the old `map-outline` waits in
    # UI-REQUESTS.md. The same icons as the tabbar (frontend/tabs.ts), which adds Settings for whoever
    # may save them, as the old shell did.
    navigation = [
        Nav("floor_plan", _("Floor plan"), "ion:apps-outline", "/table/floor-plan"),
        Nav("zones", _("Zones"), "ion:layers-outline", "/table/zones"),
        Nav("tables", _("Tables"), "ion:grid-outline", "/table/tables"),
        Nav("sessions", _("Sessions"), "ion:time-outline", "/table/sessions"),
    ]

"""The table app: the restaurant's floor plan — its zones, its tables and the checks seated at them
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav, SetupCheck, SetupStep

from apps.table.events import TABLE_EVENTS


class TableConfig(LiveAppConfig):
    name = "apps.table"
    label = "table"
    kind = "app"
    verbose_name = _("Tables")
    # Registered in the shell (ION_ICONS); `map-outline` waits in UI-REQUESTS.md.
    icon = "ion:grid-outline"
    category = Category.RESTAURANT
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    permissions = {
        "table.view_zone": _("View zones"),
        "table.add_zone": _("Create zones"),
        "table.change_zone": _("Change zones"),
        "table.delete_zone": _("Delete zones"),
        "table.view_table": _("View tables"),
        "table.add_table": _("Create tables"),
        "table.change_table": _("Change and move tables"),
        "table.delete_table": _("Delete tables"),
        "table.view_session": _("View table checks"),
        "table.add_session": _("Seat guests and open checks"),
        "table.change_session": _("Change checks: close, split, guests, park and hold"),
        "table.transfer_session": _("Move and merge checks"),
        "table.delete_session": _("Delete checks from the history"),
        "table.view_settings": _("View the settings"),
        "table.manage_settings": _("Change the settings"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The cashier (an
    # employee who also charges) is an employee.
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
    # The Home's step «Your tables», order 100 and recommended, done once one table is in use (not deleted, active:
    # an occupied or blocked one still counts), for whoever adds tables, leading to the list of tables. Refreshed on
    # what changes the tables in use; never a zone (one with tables is not deleted).
    setup = [
        SetupStep(
            key="tables",
            operation="table.floor.status",
            configured_when=[SetupCheck(field="usable_tables", truthy=True)],
            title=_("Your tables"),
            description=_(
                "Add the tables of your dining room: without them there is no order per table, no split and no transfer."
            ),
            # `map-outline` waits in UI-REQUESTS.md, as the menu's.
            icon="ion:grid-outline",
            route="/table/tables",
            permission="table.add_table",
            order=100,
            required=False,
            refresh_on=TABLE_EVENTS,
        )
    ]
    # TABLE-F29: the holds whose window passed are marked expired, every hour, by the worker as the
    # system (cron in UTC), per hub, each under ``use_hub``. Reading the plan already ignores them.
    scheduled_tasks = [
        {
            "name": "expire_table_holds",
            "operation": "table.hold.expire",
            "cron": "0 * * * *",
            "catch_up": "collapse",
        }
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only: `map-outline` waits in UI-REQUESTS.md.
    # Each entry is also a tab of the app's pages and opens with its permission: Zones, Tables and Settings,
    # to whoever may change them.
    navigation = [
        Nav("floor_plan", _("Floor plan"), "ion:apps-outline", "/table/floor-plan", permission="table.view_table"),
        Nav("zones", _("Zones"), "ion:layers-outline", "/table/zones", permission="table.change_zone"),
        Nav("tables", _("Tables"), "ion:grid-outline", "/table/tables", permission="table.change_table"),
        Nav("sessions", _("Sessions"), "ion:time-outline", "/table/sessions", permission="table.view_session"),
        Nav("settings", _("Settings"), "ion:settings-outline", "/table/settings", permission="table.manage_settings"),
    ]
    help = Help(
        flow_videos={
            "TABLE-F01": {"es": ["0S_fWROlNYc"], "en": ["Wsv-T4bTWww"]},
            "TABLE-F02": {"es": ["3UpXXiCV5Lk"], "en": ["DiPULg6x8T4"]},
            "TABLE-F04": {"es": ["3UpXXiCV5Lk"], "en": ["DiPULg6x8T4"]},
            "TABLE-F06": {"es": ["0S_fWROlNYc"], "en": ["Wsv-T4bTWww"]},
        },
    )

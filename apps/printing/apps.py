"""The printing app: the business's printers (name, connection, address, paper and what each prints), its
settings (receipt at checkout, drawer, copies, the printer of each function) and the print queue the other
apps fill by name and the device next to the printer drains (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import BellCounter, Category, LiveAppConfig, Nav, SetupCheck, SetupStep

from apps.printing.events import COVERAGE_EVENTS, UNATTENDED_EVENTS

#: The bell's row of each function, named as Printing names it (the old row showed its internal key, HUB_SHELL-F63).
NOTHING_PRINTING = {
    "receipt": _("Nothing is printing “Receipt”"),
    "kitchen": _("Nothing is printing “Kitchen”"),
    "bar": _("Nothing is printing “Bar”"),
    "label": _("Nothing is printing “Label”"),
}


class PrintingConfig(LiveAppConfig):
    name = "apps.printing"
    label = "printing"
    kind = "app"
    verbose_name = _("Printing")
    # `ion:print-outline` waits in UI-REQUESTS.md; lucide's receipt is registered and unlike invoice's.
    icon = "lucide:receipt"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _("Your receipt, kitchen and label printers, and the print queue that shows whether paper is coming out.")
    description = _(
        "Printing keeps the business's printers: their name, how they are connected (network, USB, Bluetooth "
        "or the computer's own printer), their paper and what each one prints — receipts, kitchen and bar "
        "orders or barcode labels. The till, the cash register and the inventory send their papers to the "
        "print queue, and the ERPlora app on the device next to the printer prints them. Test a printer, "
        "choose whether the receipt prints and the drawer opens at checkout, and retry or cancel a job that "
        "did not come out."
    )
    verticals = ["hair_salon", "restaurant"]
    # Nobody's models are read: whoever prints sends its document composed (printing.job.create).
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "printing.view_settings",
        "printing.manage_settings",
        "printing.print",
        "printing.manage_jobs",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old module's
    # retry and discard were the hub's administrator's: so are the queue's retry and cancel.
    role_permissions = {
        "hub_owner": ["printing.*"],
        "hub_admin": ["printing.*"],
        "hub_manager": ["printing.view_settings", "printing.manage_settings", "printing.print"],
        "hub_employee": ["printing.view_settings", "printing.print"],
    }
    # The Home's hooks (PLAN-HUB round 2026-10-21): the old hub's core item «Set up your printer» (setup_status.rs, order
    # 70, recommended: without a printer the business still sells, hub#1731), done once a device set up here reaches
    # an active receipt printer (the old «registered for the receipt station», live or not, hub#1948); and its bell row
    # «Nothing is printing “…”» (HUB_SHELL-F63, hub#987), one per function, for everybody with Printing: whoever
    # stands at the counter can switch the till back on. The old module had none of its own, nor panels.
    setup = [
        SetupStep(
            key="printer",
            operation="printing.device.coverage",
            params={"usage": "receipt"},
            configured_when=[SetupCheck(field="covered", truthy=True)],
            title=_("Set up your printer"),
            description=_("Register the device that prints your customers' receipts, so the first sale comes out on paper."),
            icon="lucide:receipt",
            route="/printing/devices",
            permission="printing.manage_settings",
            order=70,
            required=False,
            refresh_on=COVERAGE_EVENTS,
        )
    ]
    bell = [
        BellCounter(
            key=f"stalled_{usage}",
            operation="printing.device.coverage",
            params={"usage": usage},
            route="/printing/printers",
            label=label,
            icon="lucide:receipt",
            permission="printing.view_settings",
            refresh_on=UNATTENDED_EVENTS,
        )
        for usage, label in NOTHING_PRINTING.items()
    ]
    # PRINTING-F20: the queue forgets the jobs that ended (printed, cancelled, failed) over 30 days ago,
    # once an hour, as the platform (cron in UTC).
    scheduled_tasks = [
        {"name": "prune", "operation": "printing.job.prune", "cron": "23 * * * *", "catch_up": "collapse"},
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only (packages/ui/src/shell/icons.ts).
    navigation = [
        Nav("printers", _("Printers"), "lucide:receipt", "/printing/printers"),
        Nav("devices", _("Devices"), "lucide:smartphone", "/printing/devices"),
        Nav("jobs", _("Queue"), "ion:list-outline", "/printing/jobs"),
        Nav("settings", _("Settings"), "ion:settings-outline", "/printing/settings"),
    ]

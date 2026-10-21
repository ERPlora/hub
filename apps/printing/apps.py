"""The printing app: the business's printers (name, connection, address, paper and what each prints), its
settings (receipt at checkout, drawer, copies, the printer of each function) and the print queue the other
apps fill by name and the device next to the printer drains (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


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
    # PRINTING-F20: the queue forgets the jobs that ended (printed, cancelled, failed) over 30 days ago,
    # once an hour, as the platform (cron in UTC).
    scheduled_tasks = [
        {"name": "prune", "operation": "printing.job.prune", "cron": "23 * * * *", "catch_up": "collapse"},
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only (packages/ui/src/shell/icons.ts).
    navigation = [
        Nav("printers", _("Printers"), "lucide:receipt", "/printing/printers"),
        Nav("jobs", _("Queue"), "ion:list-outline", "/printing/jobs"),
        Nav("settings", _("Settings"), "ion:settings-outline", "/printing/settings"),
    ]

"""The verifactu app: the VeriFactu billing records of every document Invoicing issues, chained by their SHA-256
fingerprint, with their QR, validated against the AEAT's schemas and sent to the AEAT through ERPlora's gateway
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class VerifactuConfig(LiveAppConfig):
    name = "apps.verifactu"
    label = "verifactu"
    kind = "app"
    verbose_name = _("VeriFactu")
    icon = "lucide:shield-check"
    category = Category.SALES
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Every invoice and ticket becomes a chained VeriFactu record with its QR, sent to the AEAT."
    )
    description = _(
        "VeriFactu turns every document Invoicing issues into its billing record for the Spanish tax agency: "
        "chained to the previous one by its SHA-256 fingerprint, with the QR the customer can check, validated "
        "against the AEAT's official schemas and sent in order, respecting the waiting time the AEAT asks for. "
        "What cannot go out waits in the queue and leaves by itself; a rejected record is corrected with a new one. "
        "Records, queue, audit events and the chain's recovery are all here, in the test environment until you go "
        "live."
    )
    verticals = ["hair_salon", "restaurant"]
    # A record is born from an issued invoice, read from its row (a foreign key).
    requires = ["invoice"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "verifactu.view_record",
        "verifactu.add_record",
        "verifactu.transmit_record",
        "verifactu.correct_record",
        "verifactu.configure",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). Receiving the account's
    # photo (``verifactu.sync_config``) is declared by no role: only the system holds it.
    role_permissions = {
        "hub_owner": ["verifactu.*"],
        "hub_admin": ["verifactu.*"],
        "hub_manager": [
            "verifactu.view_record",
            "verifactu.add_record",
            "verifactu.transmit_record",
        ],
        "hub_employee": ["verifactu.view_record", "verifactu.add_record"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =` as the
    # module's own icon. Registered icons only (packages/ui/src/shell/icons.ts): the old document-text-outline
    # and shield-checkmark-outline wait in UI-REQUESTS.md.
    navigation = [
        Nav("records", _("Records"), "ion:list-outline", "/verifactu/records"),
        Nav(
            "contingency",
            _("Contingency"),
            "ion:warning-outline",
            "/verifactu/contingency",
        ),
        Nav("events", _("Events"), "ion:time-outline", "/verifactu/events"),
        Nav("recovery", _("Recovery"), "lucide:shield-check", "/verifactu/recovery"),
        Nav("config", _("Configuration"), "ion:key-outline", "/verifactu/config"),
        Nav("settings", _("Settings"), "ion:settings-outline", "/verifactu/settings"),
    ]
    # The queue's send (VERIFACTU-F20): the phase-2 worker runs it on every hub as the system, every minute
    # (cron in UTC); each chain waits the TiempoEsperaEnvio the AEAT answered.
    scheduled_tasks = [
        {
            "name": "process_queue",
            "operation": "verifactu.contingency.process",
            "cron": "* * * * *",
            "catch_up": "collapse",
        }
    ]

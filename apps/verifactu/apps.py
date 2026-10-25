"""The verifactu app: the VeriFactu billing records of every document Invoicing issues, chained by their SHA-256
fingerprint, with their QR, validated against the AEAT's schemas and sent to the AEAT through ERPlora's gateway
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep, Widget

from apps.verifactu import events as E

VIEW = "verifactu.view_record"


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
    # The Home's hooks (PLAN-HUB round 2026-10-21), the old module's module.json `setup` and `widgets` (it had no
    # `bell`). The step is done once the chosen way could carry the records to the AEAT of production (VERIFACTU-F08,
    # no plan gating it: PLAN §30), which is what the business has to do. Its level is base's: functional in testing,
    # which files without it while the till sells (gh:hub#1726); ⛔ legal where the hub files in production, which
    # refuses every sale without it (``base.home.LEGAL_IN_PRODUCTION``, on the row's ``environment``). The panels read the queries of the old ones, each
    # refreshed by the events live.py re-runs it on; the latest events are a component of the app, which names each
    # event's type in the reader's language (gh:verifactu#139). Registered icons only: the old
    # `shield-checkmark-outline` and `stats-chart-outline` wait in UI-REQUESTS.md.
    setup = [
        SetupStep(
            key="sending_route",
            operation="verifactu.config.get",
            configured_when=[SetupCheck(field="route_ready_for_production", truthy=True)],
            title=_("Set up VeriFactu"),
            description=_(
                "Sign the authorisation for ERPlora to send your invoices to the AEAT, or upload your business "
                "certificate."
            ),
            icon="lucide:shield-check",
            route="/verifactu/config",
            permission="verifactu.configure",
            required=True,
            refresh_on=[E.CONFIG_CHANGED],
        )
    ]
    widgets = [
        Widget(
            key="pending",
            title=_("VeriFactu pending"),
            icon="lucide:shield-check",
            size="sm",
            permission=VIEW,
            default=True,
            refresh_on=E.RECORD_EVENTS,
            kind="kpi",
            operation="verifactu.stats.compliance_summary",
            map={"value": "pending_count"},
            options={"format": "number"},
        ),
        Widget(
            key="contingency",
            title=_("Contingency queue"),
            icon="ion:warning-outline",
            size="sm",
            permission=VIEW,
            refresh_on=E.RECORD_EVENTS,
            kind="stat",
            operation="verifactu.stats.contingency_summary",
            map={"value": "queued_count", "severity": "severity"},
            options={"format": "number", "label": _("In contingency queue")},
        ),
        Widget(
            key="by_status",
            title=_("Records by status"),
            icon="ion:list-outline",
            size="md",
            permission=VIEW,
            refresh_on=E.RECORD_EVENTS,
            kind="bar-list",
            operation="verifactu.stats.records_by_status",
            map={"label": "label", "value": "total"},
            options={"valueFormat": "number"},
        ),
        Widget(
            key="events",
            title=_("Recent AEAT events"),
            icon="ion:time-outline",
            size="md",
            permission=VIEW,
            refresh_on=E.ALL,
            component="RecentEventsPanel",
        ),
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

    def can_disable(self, ctx) -> str | None:
        """VERIFACTU-F32: the platform's ``base.app.disable`` asks before turning the app off: refused, with how many,
        while a record is not in the AEAT yet (``queries.disable_refusal``), whose send would stop."""
        from apps.verifactu import queries  # the models are not loaded yet when this module is

        return queries.disable_refusal(ctx)

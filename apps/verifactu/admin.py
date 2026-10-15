"""Django admin of the verifactu app, for the platform's staff only (round 12, PLAN §17; hubs.erplora.com).

Nothing fiscal is typed here: every model is shown whole and read-only, never added, changed nor deleted.
- What was sealed (records, chain heads, audit events, the AEAT's photo) never changes: it is corrected with a new
  record (RD 1007/2023) and the records are kept.
- The configuration moves only through its operations, which hold the law's guards: the route through
  ``verifactu.config.update``, the environment through ``go_live`` / ``back_to_testing``, the authorisation, the
  live option and the hub's status through the SaaS's photo. Typing them here would file under ERPlora's seal
  without the approved authorisation, or skip the AEAT's waiting time (the send control).
- Own certificate: its holder, kind and expiry only; never its sealed material (the .p12 and its password).
- Records: the columns and filters of the module's records screen, and one action, «Resend to the AEAT», that runs
  ``verifactu.record.transmit`` for the hub chosen in the admin session (``/admin/hub/<slug>/``), as the staff
  member. **Round to write in PLAN §17**: CLAUDE.md says «full CRUD… fiscal ones included»; here the law keeps
  the fiscal tables read-only and their changes are operations.
"""

from decimal import Decimal

from django.contrib import admin, messages
from django.utils.formats import number_format
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.operations import get

from apps.verifactu.models import (
    AeatRecord,
    Chain,
    Config,
    Event,
    OwnCertificate,
    Record,
    SendControl,
)
from base.admin import ADMIN_HUB_SESSION_KEY

RESEND = _("Resend to the AEAT")
RESENT = _(
    "Resend finished: %(accepted)s accepted, %(rejected)s rejected, %(waiting)s still waiting."
)
CHOOSE_A_HUB = _(
    "Choose a hub first (its link in the SaaS admin): the action runs on that hub."
)
INVOICE_PART = _("Invoice")
CHAIN_PART = _("Hash chain")
AEAT_PART = _("AEAT response")
METADATA_PART = _("Metadata")


class ReadOnlyAdmin(admin.ModelAdmin):
    """Every field shown, none typed; nothing added, changed or deleted."""

    def get_readonly_fields(self, request, obj=None) -> tuple:
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Config)
class ConfigAdmin(ReadOnlyAdmin):
    list_display = (
        "environment",
        "route",
        "representation_status",
        "live_paid",
        "hub_status",
        "synced_at",
    )


@admin.register(OwnCertificate)
class OwnCertificateAdmin(admin.ModelAdmin):
    """Whose it is and until when; the sealed material is never a field here."""

    list_display = ("holder", "holder_tax_id", "kind", "expires_at", "uploaded_at")
    fields = ("holder", "holder_tax_id", "kind", "expires_at", "uploaded_at", "uploaded_by")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Chain)
class ChainAdmin(ReadOnlyAdmin):
    list_display = (
        "issuer_nif",
        "environment",
        "sequence",
        "last_number",
        "anchor_source",
        "validation_valid",
    )
    list_filter = ("environment",)
    search_fields = ("issuer_nif", "last_number")


@admin.register(SendControl)
class SendControlAdmin(ReadOnlyAdmin):
    list_display = (
        "issuer_nif",
        "environment",
        "next_send_at",
        "wait_seconds",
        "last_sent_at",
    )


def _staff_context(request) -> OperationContext | None:
    slug = request.session.get(ADMIN_HUB_SESSION_KEY)
    if not slug:
        return None
    return OperationContext(
        scope=Scope("host", slug),
        actor=request.user,
        permissions=frozenset({"verifactu.transmit_record"}),
        language=getattr(request, "LANGUAGE_CODE", "en"),
        request=request,
    )


@admin.register(Record)
class RecordAdmin(ReadOnlyAdmin):
    list_display = (
        "sequence",
        "invoice_number",
        "issue_date",
        "record_type",
        "issuer_nif",
        "total",
        "environment",
        "status",
        "csv",
    )
    list_filter = ("status", "record_type", "invoice_type", "environment")
    search_fields = (
        "invoice_number",
        "issuer_nif",
        "issuer_name",
        "fingerprint",
        "csv",
    )
    date_hierarchy = "issue_date"
    fieldsets = (
        (
            INVOICE_PART,
            {
                "fields": (
                    "record_type",
                    "environment",
                    "issuer_nif",
                    "issuer_name",
                    "sequence",
                    "invoice",
                    "invoice_number",
                    "issue_date",
                    "operation_date",
                    "invoice_type",
                    "rectification_kind",
                    "rectified",
                    "substituted",
                    "description",
                    "recipient_name",
                    "recipient_tax_id",
                    "recipient_country",
                    "recipient_id_type",
                    "tax_breakdown",
                    "base_amount",
                    "tax_amount",
                    "total_amount",
                    "correction",
                    "previous_rejection",
                    "corrects",
                    "cancels",
                )
            },
        ),
        (
            CHAIN_PART,
            {
                "fields": (
                    "previous_record",
                    "previous_issuer_nif",
                    "previous_number",
                    "previous_issue_date",
                    "previous_fingerprint",
                    "generated_at",
                    "generated_on",
                    "fingerprint",
                    "qr_url",
                )
            },
        ),
        (
            AEAT_PART,
            {
                "fields": (
                    "status",
                    "attempts",
                    "next_attempt_at",
                    "wait_reason",
                    "wait_detail",
                    "transmitted_at",
                    "transmission_id",
                    "envelope_digest",
                    "incident",
                    "csv",
                    "aeat_code",
                    "aeat_message",
                )
            },
        ),
        (
            Record._meta.get_field("xml").verbose_name,
            {"fields": ("xml", "xml_built_at"), "classes": ("collapse",)},
        ),
        (
            METADATA_PART,
            {
                "fields": ("id", "created_at", "created_by", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ["resend_to_aeat"]

    @admin.display(
        description=Record._meta.get_field("total_amount").verbose_name,
        ordering="total_amount",
    )
    def total(self, record: Record) -> str | None:
        if record.total_amount is None:
            return None
        return f"{number_format(Decimal(record.total_amount) / 100, 2)} €"

    @admin.action(description=RESEND)
    def resend_to_aeat(self, request, queryset) -> None:
        """Sends each chosen chain now: ``verifactu.record.transmit`` on its latest chosen record carries the
        earlier ones of its chain, so each chain goes once."""
        ctx = _staff_context(request)
        if ctx is None:
            self.message_user(request, str(CHOOSE_A_HUB), messages.ERROR)
            return
        transmit = get("verifactu.record.transmit")
        totals = {"accepted": 0, "rejected": 0, "waiting": 0}
        sent_chains: set[tuple[str, str]] = set()
        ran = False
        for record in sorted(queryset, key=lambda item: item.sequence, reverse=True):
            chain = (record.issuer_nif, record.environment)
            if record.status in Record.UNSENT:
                if chain in sent_chains:
                    continue
                sent_chains.add(chain)
            try:
                out = transmit(
                    ctx, transmit.input.model_validate({"record_id": str(record.id)})
                )
            except OperationError as refusal:
                self.message_user(
                    request, f"{record.invoice_number}: {refusal.message}", messages.WARNING
                )
                continue
            ran = True
            totals["accepted"] += out.accepted + out.accepted_with_errors
            totals["rejected"] += out.rejected
            totals["waiting"] += out.waiting
            if out.reason:
                self.message_user(
                    request, f"{record.invoice_number}: {out.message}", messages.WARNING
                )
        if ran:
            clean = totals["rejected"] == totals["waiting"] == 0
            self.message_user(
                request,
                str(RESENT) % totals,
                messages.SUCCESS if clean else messages.WARNING,
            )


@admin.register(Event)
class EventAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "kind", "severity", "message_key", "record", "actor")
    list_filter = ("kind", "severity")
    search_fields = ("search_text",)


@admin.register(AeatRecord)
class AeatRecordAdmin(ReadOnlyAdmin):
    list_display = (
        "invoice_number",
        "issuer_nif",
        "environment",
        "state",
        "generated_on",
        "queried_at",
    )
    list_filter = ("environment",)
    search_fields = ("invoice_number", "issuer_nif")

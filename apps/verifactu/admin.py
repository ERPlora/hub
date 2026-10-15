"""Django admin of the verifactu app, for the platform's staff only (round 12, PLAN §17; hubs.erplora.com).

- Configuration: edited (the route and what the ERPlora account sends), except its environment, which moves
  only through ``verifactu.config.go_live`` / ``back_to_testing`` (their guards are the law's).
- Own certificate: its holder, kind and expiry only, read-only; never its sealed material (the .p12 and its
  password), which only ``verifactu.certificate.upload`` / ``remove`` write.
- Chain heads, records, audit events and the AEAT's photo: shown whole and read-only, never added (only the
  operations seal, with the chain's lock) nor deleted (the records are kept: RD 1007/2023). **Round to write
  in PLAN §17**: CLAUDE.md says «full CRUD… fiscal ones included»; here, as in Invoicing, the law keeps what
  was sealed read-only.
- Send control: only its AEAT wait (``next_send_at``) can be released.
- «Send now» and «Retry» run ``verifactu.record.transmit`` and ``verifactu.contingency.retry`` for the hub
  chosen in the admin session (``/admin/hub/<slug>/``), as the staff member.
"""

from django.contrib import admin, messages
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

DONE = {
    "verifactu.record.transmit": _("sent to the AEAT through ERPlora's gateway."),
    "verifactu.contingency.retry": _("goes out with the next pass."),
}
SEND_NOW = _("Send now")
RETRY = _("Retry with the next pass")
CHOOSE_A_HUB = _(
    "Choose a hub first (its link in the SaaS admin): the action runs on that hub."
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Every field shown, none typed; nothing added or deleted."""

    def get_readonly_fields(self, request, obj=None) -> tuple:
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = (
        "environment",
        "route",
        "representation_status",
        "synced_at",
    )
    readonly_fields = (
        "id",
        "singleton",
        "environment",
        "production_since",
        "synced_at",
        "updated_at",
        "updated_by",
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
class SendControlAdmin(admin.ModelAdmin):
    list_display = (
        "issuer_nif",
        "environment",
        "next_send_at",
        "wait_seconds",
        "last_sent_at",
    )

    def get_readonly_fields(self, request, obj=None) -> tuple:
        return tuple(
            field.name
            for field in SendControl._meta.concrete_fields
            if field.name != "next_send_at"
        )

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


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
        "record_type",
        "invoice_type",
        "issuer_nif",
        "environment",
        "status",
        "attempts",
        "created_at",
    )
    list_filter = ("environment", "status", "record_type", "invoice_type")
    search_fields = (
        "invoice_number",
        "issuer_nif",
        "issuer_name",
        "fingerprint",
        "csv",
    )
    actions = ["send_now", "retry"]

    def _run(self, request, queryset, operation: str) -> None:
        ctx = _staff_context(request)
        if ctx is None:
            self.message_user(request, str(CHOOSE_A_HUB), messages.ERROR)
            return
        op = get(operation)
        for record in queryset:
            try:
                op(ctx, op.input.model_validate({"record_id": str(record.id)}))
            except OperationError as refusal:
                self.message_user(
                    request,
                    f"{record.invoice_number}: {refusal.message}",
                    messages.WARNING,
                )
            else:
                self.message_user(
                    request,
                    f"{record.invoice_number}: {DONE[operation]}",
                    messages.SUCCESS,
                )


    @admin.action(description=SEND_NOW)
    def send_now(self, request, queryset) -> None:
        self._run(request, queryset, "verifactu.record.transmit")

    @admin.action(description=RETRY)
    def retry(self, request, queryset) -> None:
        self._run(request, queryset, "verifactu.contingency.retry")


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

"""Django admin of the verifactu app, for the platform's staff only (round 12, PLAN §17; hubs.erplora.com), at the
service of support. Ioan's criterion (2026-10-15): a record not sent is not a record registered; support does not
delete a sale, it fixes a sending problem.

- What was sealed (records, chain heads, audit events, the AEAT's photo) is shown whole and never typed, added nor
  deleted: it is corrected with a new record (RD 1007/2023) and the records are kept. A record the AEAT registered
  (accepted, accepted with errors) is never touched by any action here.
- What is not registered yet (pending, sent without an answer, rejected) is worked on with actions that are the
  module's operations, run for the hub chosen in the admin session (``/admin/hub/<slug>/``) as the staff member,
  so their guards apply and they leave their audit event: «Resend to the AEAT» (``verifactu.record.transmit``),
  «Reschedule» (``verifactu.contingency.retry``), «Ask the AEAT» (``verifactu.record.reconcile``: a record leaves
  the queue only when the AEAT holds that very record) and, for a rejection, «Correct with a new record»
  (``verifactu.record.correct``). Nothing leaves the queue that the AEAT does not hold.
- The AEAT's waiting time (``SendControl.next_send_at``, its ``TiempoEsperaEnvio``) is never shortened: rescheduling
  puts the records out with the next pass, which goes as soon as the AEAT lets it. A record's ``wait_reason`` is
  kept until that pass: it is what declares the record late (``Incidencia`` S).
- The configuration: only the route is chosen here, through ``verifactu.config.update`` (its refusal is the form's
  error). The environment moves through ``go_live`` / ``back_to_testing``; the authorisation and the business's
  status come from the SaaS's photo (the retired live option is not shown); the certificate is uploaded in the
  module. None is typed here.
- Own certificate: its holder, kind and expiry only; never its sealed material (the .p12 and its password).
"""

from contextvars import ContextVar
from decimal import Decimal

from babel.numbers import format_decimal
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import translation
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
    wait_reason_text,
)
from apps.verifactu.queries import config_row, waiting_of
from base.admin import ADMIN_HUB_SESSION_KEY

#: What the staff may run here: send and ask the AEAT, correct a rejection, choose the route.
STAFF_PERMISSIONS = frozenset(
    {"verifactu.transmit_record", "verifactu.correct_record", "verifactu.configure"}
)

RESEND = _("Resend to the AEAT")
RESENT = _(
    "Resend finished: %(accepted)s accepted, %(rejected)s rejected, %(waiting)s still waiting."
)
RESCHEDULE = _("Reschedule: send with the next pass")
RESCHEDULED = _("Rescheduled: %(count)s record(s) go out with the next pass.")
RESCHEDULE_CHAIN = _("Reschedule its queue: send with the next pass")
CHAINS_RESCHEDULED = _("Rescheduled: %(count)s chain(s) go out with the next pass.")
NOTHING_WAITING = _("nothing is waiting in its queue.")
ASK_THE_AEAT = _("Ask the AEAT (out of the queue if it already has it)")
ASKED = _(
    "Asked the AEAT: %(held)s already registered (out of the queue), %(missing)s not in the AEAT (still in the queue)."
)
CORRECT_REJECTION = _("Correct a rejection with a new record")
CORRECTED = _("Corrected: %(count)s new record(s) in the queue.")
ONLY_REJECTED_REGISTERED = _(
    "only a record the AEAT rejected is corrected here; this one is registered."
)
ONLY_REJECTED_QUEUED = _(
    "only a record the AEAT rejected is corrected here; this one is still in the queue."
)
CHOOSE_A_HUB = _(
    "Choose a hub first (its link in the SaaS admin): the action runs on that hub."
)
WHY_WAITING = _("Why it is not in the AEAT yet")
INVOICE_PART = _("Invoice")
CHAIN_PART = _("Hash chain")
AEAT_PART = _("AEAT response")
METADATA_PART = _("Metadata")


#: The hub chosen in the admin session while a record's page is drawn: ``why_waiting`` gets no request, and why a
#: record waits depends on whose hub it is (ERPlora's own files ERPlora's records without an authorisation).
_drawn_for: ContextVar[Scope | None] = ContextVar("verifactu_admin_drawn_for", default=None)


def _staff_context(request) -> OperationContext | None:
    """The staff member on the hub chosen in the admin session; ``None`` without one."""
    slug = request.session.get(ADMIN_HUB_SESSION_KEY)
    if not slug:
        return None
    return OperationContext(
        scope=Scope("host", slug),
        actor=request.user,
        permissions=STAFF_PERMISSIONS,
        language=getattr(request, "LANGUAGE_CODE", "en"),
        request=request,
    )


def _run(ctx: OperationContext, name: str, data: dict):
    """The operation ``name`` with ``data`` validated as its route would."""
    operation = get(name)
    return operation(ctx, operation.input.model_validate(data))


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


class SupportActions:
    """The actions' plumbing: the staff's context or a message saying a hub is missing, and each refusal of an
    operation told with the invoice it was about."""

    def _context(self, request) -> OperationContext | None:
        ctx = _staff_context(request)
        if ctx is None:
            self.message_user(request, str(CHOOSE_A_HUB), messages.ERROR)
        return ctx

    def _attempt(self, request, ctx, label: str, name: str, record_id) -> object | None:
        try:
            return _run(ctx, name, {"record_id": str(record_id)})
        except OperationError as refusal:
            self.message_user(request, f"{label}: {refusal.message}", messages.WARNING)
            return None


class ConfigForm(forms.ModelForm):
    """Only the route; choosing it IS ``verifactu.config.update``, run when the form is validated so that its
    refusal (no valid own certificate, no approved authorisation…) is the form's error. ``request`` is set by
    ``ConfigAdmin.get_form``."""

    request = None

    class Meta:
        model = Config
        fields = ("route",)

    def clean(self):
        cleaned = super().clean()
        if self.errors or "route" not in self.changed_data:
            return cleaned
        ctx = _staff_context(self.request)
        if ctx is None:
            raise ValidationError(str(CHOOSE_A_HUB))
        try:
            _run(ctx, "verifactu.config.update", {"route": cleaned["route"]})
        except OperationError as refusal:
            raise ValidationError(refusal.message) from None
        return cleaned


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    """Seen whole; the route chosen through its operation; nothing added nor deleted."""

    form = ConfigForm
    list_display = (
        "environment",
        "route",
        "representation_status",
        "hub_status",
        "synced_at",
    )

    def get_readonly_fields(self, request, obj=None) -> tuple:
        return tuple(
            field.name
            for field in Config._meta.concrete_fields
            # ``live_paid`` is retired (PLAN §30): its column only waits to be dropped.
            if field.name not in ("route", "live_paid")
        )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        form.request = request
        return form

    def save_model(self, request, obj, form, change) -> None:
        """Nothing to write: the operation saved the route (and its event) when the form was validated."""

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(OwnCertificate)
class OwnCertificateAdmin(admin.ModelAdmin):
    """Whose it is and until when; the sealed material is never a field here."""

    list_display = ("holder", "holder_tax_id", "kind", "expires_at", "uploaded_at")
    fields = (
        "holder",
        "holder_tax_id",
        "kind",
        "expires_at",
        "uploaded_at",
        "uploaded_by",
    )
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
class SendControlAdmin(SupportActions, ReadOnlyAdmin):
    """The AEAT's waiting time of each chain, never typed; its queue is rescheduled through the operation."""

    list_display = (
        "issuer_nif",
        "environment",
        "next_send_at",
        "wait_seconds",
        "last_sent_at",
    )
    actions = ["reschedule_chain"]

    @admin.action(description=RESCHEDULE_CHAIN)
    def reschedule_chain(self, request, queryset) -> None:
        """``verifactu.contingency.retry`` on the newest record waiting in each chain: it carries the earlier ones."""
        ctx = self._context(request)
        if ctx is None:
            return
        count = 0
        for control in queryset:
            newest = (
                Record.objects.filter(
                    issuer_nif=control.issuer_nif,
                    environment=control.environment,
                    status__in=Record.UNSENT,
                )
                .order_by("-sequence")
                .first()
            )
            if newest is None:
                self.message_user(
                    request, f"{control}: {NOTHING_WAITING}", messages.WARNING
                )
                continue
            out = self._attempt(
                request, ctx, str(control), "verifactu.contingency.retry", newest.id
            )
            count += out is not None
        if count:
            self.message_user(
                request, str(CHAINS_RESCHEDULED) % {"count": count}, messages.SUCCESS
            )


class WaitReasonFilter(admin.SimpleListFilter):
    """Why the records wait, in the reader's language; only the reasons some record has."""

    title = Record._meta.get_field("wait_reason").verbose_name
    parameter_name = "wait_reason"

    def lookups(self, request, model_admin):
        codes = (
            model_admin.get_queryset(request)
            .exclude(wait_reason="")
            .order_by("wait_reason")
            .values_list("wait_reason", flat=True)
            .distinct()
        )
        return [(code, wait_reason_text(code, "…", "…")) for code in codes]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(wait_reason=self.value())
        return queryset


@admin.register(Record)
class RecordAdmin(SupportActions, ReadOnlyAdmin):
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
    list_filter = (
        "status",
        WaitReasonFilter,
        "record_type",
        "invoice_type",
        "environment",
    )
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
                    "why_waiting",
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
    actions = ["resend_to_aeat", "reschedule", "ask_the_aeat", "correct_rejection"]

    def get_readonly_fields(self, request, obj=None) -> tuple:
        return (*super().get_readonly_fields(request, obj), "why_waiting")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """The page drawn for the hub chosen in the session (``why_waiting``), before the choice is forgotten."""
        ctx = _staff_context(request)
        token = _drawn_for.set(ctx.scope if ctx else None)
        try:
            response = super().change_view(request, object_id, form_url, extra_context)
            if hasattr(response, "render"):
                response.render()
            return response
        finally:
            _drawn_for.reset(token)

    @admin.display(
        description=Record._meta.get_field("total_amount").verbose_name,
        ordering="total_amount",
    )
    def total(self, record: Record) -> str | None:
        if record.total_amount is None:
            return None
        # Thousands always grouped with the screens' marks («1.234,56 €»; hub#1090): Django's Spanish format
        # groups with a space.
        locale = translation.to_locale(translation.get_language() or "en")
        return f"{format_decimal(Decimal(record.total_amount) / 100, format='#,##0.00', locale=locale)} €"

    @admin.display(description=WHY_WAITING)
    def why_waiting(self, record: Record) -> str:
        reasons = waiting_of(record, config_row(), _drawn_for.get())
        return "; ".join(reason["message"] for reason in reasons) or "—"

    @admin.action(description=RESEND)
    def resend_to_aeat(self, request, queryset) -> None:
        """Sends each chosen chain now: ``verifactu.record.transmit`` on its latest chosen record carries the
        earlier ones of its chain, so each chain goes once."""
        ctx = self._context(request)
        if ctx is None:
            return
        totals = {"accepted": 0, "rejected": 0, "waiting": 0}
        sent_chains: set[tuple[str, str]] = set()
        ran = False
        for record in sorted(queryset, key=lambda item: item.sequence, reverse=True):
            chain = (record.issuer_nif, record.environment)
            if record.status in Record.UNSENT:
                if chain in sent_chains:
                    continue
                sent_chains.add(chain)
            out = self._attempt(
                request,
                ctx,
                record.invoice_number,
                "verifactu.record.transmit",
                record.id,
            )
            if out is None:
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

    @admin.action(description=RESCHEDULE)
    def reschedule(self, request, queryset) -> None:
        """``verifactu.contingency.retry`` on each chosen record: out with the next pass, within the AEAT's wait."""
        ctx = self._context(request)
        if ctx is None:
            return
        count = 0
        for record in queryset.order_by("sequence"):
            out = self._attempt(
                request,
                ctx,
                record.invoice_number,
                "verifactu.contingency.retry",
                record.id,
            )
            count += out is not None
        if count:
            self.message_user(
                request, str(RESCHEDULED) % {"count": count}, messages.SUCCESS
            )

    @admin.action(description=ASK_THE_AEAT)
    def ask_the_aeat(self, request, queryset) -> None:
        """``verifactu.record.reconcile`` on each chosen record: it leaves the queue only if the AEAT holds it."""
        ctx = self._context(request)
        if ctx is None:
            return
        tally = {"held": 0, "missing": 0}
        for record in queryset.order_by("sequence"):
            out = self._attempt(
                request,
                ctx,
                record.invoice_number,
                "verifactu.record.reconcile",
                record.id,
            )
            if out is not None:
                tally["held" if out.held else "missing"] += 1
        if tally["held"] or tally["missing"]:
            self.message_user(
                request,
                str(ASKED) % tally,
                messages.WARNING if tally["missing"] else messages.SUCCESS,
            )

    @admin.action(description=CORRECT_REJECTION)
    def correct_rejection(self, request, queryset) -> None:
        """``verifactu.record.correct`` on each chosen rejection: a new record enters the queue, the rejected one stays;
        a registered record is never corrected from here."""
        ctx = self._context(request)
        if ctx is None:
            return
        count = 0
        for record in queryset.order_by("sequence"):
            if record.status != Record.Status.REJECTED:
                why = (
                    ONLY_REJECTED_QUEUED
                    if record.status in Record.UNSENT
                    else ONLY_REJECTED_REGISTERED
                )
                self.message_user(
                    request, f"{record.invoice_number}: {why}", messages.WARNING
                )
                continue
            out = self._attempt(
                request,
                ctx,
                record.invoice_number,
                "verifactu.record.correct",
                record.id,
            )
            count += out is not None
        if count:
            self.message_user(
                request, str(CORRECTED) % {"count": count}, messages.SUCCESS
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

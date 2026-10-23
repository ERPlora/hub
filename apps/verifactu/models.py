"""Models of the verifactu app (WORKBOOK «Para quien lo mantiene»).

- ``Config``: one row; the environment (testing or production), the route (ERPlora files, or the business's own
  certificate) and what the ERPlora account sends (the authorisation's state, the business's status).
- ``OwnCertificate``: one row at most; the business's own certificate, uploaded here (VERIFACTU-F02): its holder,
  kind and expiry, and the .p12 with its password sealed together (``certificates.seal``). The sealed blob is
  never shown: not in ``str``, the admin, the API nor the photo.
- ``Chain``: the head of a chain, one per ``(issuer NIF, environment)``: the last sequence and the last record's
  fingerprint, number and date. Sealing a record locks it.
- ``SendControl``: the queue's control row, one per ``(issuer NIF, environment)``: ``next_send_at`` (the AEAT's
  ``TiempoEsperaEnvio``) and the send's lock (``SKIP LOCKED``), apart from ``Chain`` so a send never holds the
  till.
- ``Record``: a billing record (alta or anulación), sealed once and never edited in its fiscal data or its XML;
  its status, answer and attempts move. The records that are not in the AEAT yet are the queue.
- ``Event``: the audit trail, its message composed in the reader's language from a key and its parameters.
- ``AeatRecord``: the last photo of what the AEAT holds (replaced by each query).

Money is in whole cents with a sign. Phase 1 has no tenancy (like ``apps.invoice``).
"""

import datetime as dt

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import Exact
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

NIF_MAX_LENGTH = 32
NUMBER_MAX_LENGTH = 60
ACTOR_MAX_LENGTH = 128
FINGERPRINT_LENGTH = 64
#: The first wait after a failed send, doubled each time up to an hour (5, 10, 20, 40, 60, 60…).
FIRST_WAIT_MINUTES = 5
MAX_WAIT_MINUTES = 60


def backoff(attempts: int) -> dt.timedelta:
    """How long a record waits after its ``attempts``-th failed send."""
    return dt.timedelta(
        minutes=min(FIRST_WAIT_MINUTES * 2 ** max(attempts - 1, 0), MAX_WAIT_MINUTES)
    )


class Environment(models.TextChoices):
    TESTING = "testing", _("Testing (AEAT test)")
    PRODUCTION = "production", _("Production")


class Config(UUIDModel):
    Environment = Environment

    class Route(models.TextChoices):
        ERPLORA = "erplora", _("ERPlora files for you")
        OWN = "own", _("With my own certificate")

    class Representation(models.TextChoices):
        NONE = "none", _("Not signed")
        SUBMITTED = "submitted", _("Under review")
        APPROVED = "approved", _("Approved")
        RETURNED = "returned", _("Returned")
        REVOKED = "revoked", _("Revoked")

    class HubStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        PAST_DUE = "past_due", _("Payment pending")
        SUSPENDED = "suspended", _("Suspended")

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    environment = models.CharField(
        _("environment"),
        max_length=10,
        choices=Environment.choices,
        default=Environment.TESTING,
    )
    route = models.CharField(
        _("sending route"), max_length=8, choices=Route.choices, default=Route.ERPLORA
    )
    production_since = models.DateTimeField(
        _("in production since"), null=True, blank=True
    )
    representation_status = models.CharField(
        _("representation"),
        max_length=10,
        choices=Representation.choices,
        default=Representation.NONE,
    )
    representation_updated_at = models.DateTimeField(
        _("representation updated at"), null=True, blank=True
    )
    representation_reason = models.CharField(
        _("representation note"), max_length=500, blank=True
    )
    # Retired (PLAN §30, round 2026-10-22b: VeriFactu on Free): no plan gates production any more, so nothing reads
    # nor writes it. The column stays until a later contract step drops it: the tasks of the previous deployment
    # still read it while the new one rolls out.
    live_paid = models.BooleanField(_("live option in the plan"), default=False)
    # From the ERPlora account's photo: the business's commercial status; going live needs it active
    # (``queries.live_problems``).
    hub_status = models.CharField(
        _("business status"),
        max_length=10,
        choices=HubStatus.choices,
        default=HubStatus.ACTIVE,
    )
    # The business's id in ERPlora (the SaaS's ``Hub.id``), told by the photo's path: where the signed authorisation
    # is sent (VERIFACTU-F05). Phase 2 reads it from the control registry.
    hub_id = models.UUIDField(_("ERPlora business id"), null=True, blank=True)
    synced_version = models.BigIntegerField(_("synced version"), null=True, blank=True)
    synced_at = models.DateTimeField(_("synced at"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("configuration")
        verbose_name_plural = _("configuration")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="verifactu_config_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="verifactu_config_singleton"
            ),
        ]

    def __str__(self) -> str:
        return str(_("VeriFactu configuration"))


class OwnCertificate(UUIDModel):
    """The business's own certificate (VERIFACTU-F02): one at most, its material sealed (``certificates.seal``)."""

    class Kind(models.TextChoices):
        SEAL = "seal", _("Electronic seal")
        REPRESENTATIVE = "representative", _("Representative of an entity")
        PERSONAL = "personal", _("Personal")
        UNKNOWN = "unknown", _("Other")

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    holder = models.CharField(_("holder"), max_length=200)
    holder_tax_id = models.CharField(_("holder's tax ID"), max_length=20)
    kind = models.CharField(_("kind"), max_length=14, choices=Kind.choices)
    expires_at = models.DateTimeField(_("expires at"))
    uploaded_at = models.DateTimeField(_("uploaded at"), default=timezone.now)
    uploaded_by = models.CharField(
        _("uploaded by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    sealed_blob = models.BinaryField(_("sealed certificate"), editable=False)

    class Meta:
        verbose_name = _("own certificate")
        verbose_name_plural = _("own certificate")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="verifactu_owncertificate_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="verifactu_owncertificate_singleton"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.holder} ({self.holder_tax_id})"


class Chain(UUIDModel):
    """The head of the chain of one issuer in one environment."""

    issuer_nif = models.CharField(_("issuer tax ID"), max_length=NIF_MAX_LENGTH)
    environment = models.CharField(
        _("environment"), max_length=10, choices=Environment.choices
    )
    # The last sequence given; the next record takes sequence + 1.
    sequence = models.PositiveIntegerField(_("last sequence"), default=0)
    last_record = models.ForeignKey(
        "Record",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("last record"),
    )
    # What Encadenamiento/RegistroAnterior names: the last record's, or an anchor's (recovery, migration).
    last_issuer_nif = models.CharField(
        _("previous issuer"), max_length=NIF_MAX_LENGTH, blank=True
    )
    last_number = models.CharField(
        _("previous invoice"), max_length=NUMBER_MAX_LENGTH, blank=True
    )
    last_issue_date = models.DateField(
        _("previous invoice date"), null=True, blank=True
    )
    last_fingerprint = models.CharField(
        _("previous fingerprint"), max_length=FINGERPRINT_LENGTH, blank=True
    )
    anchored_at = models.DateTimeField(_("anchored at"), null=True, blank=True)
    anchor_source = models.CharField(_("anchor"), max_length=8, blank=True)
    validated_at = models.DateTimeField(_("validated at"), null=True, blank=True)
    validation_valid = models.BooleanField(_("chain intact"), null=True, blank=True)
    validation_total = models.PositiveIntegerField(_("records validated"), default=0)
    validation_first_invalid = models.PositiveIntegerField(
        _("first broken sequence"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("chain")
        verbose_name_plural = _("chains")
        ordering = ["issuer_nif", "environment"]
        constraints = [
            models.UniqueConstraint(
                fields=["issuer_nif", "environment"],
                name="verifactu_chain_per_issuer_env",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.issuer_nif} ({self.environment})"


class SendControl(UUIDModel):
    """The queue's control row of one chain: when the AEAT lets it send again, and the send's lock."""

    issuer_nif = models.CharField(_("issuer tax ID"), max_length=NIF_MAX_LENGTH)
    environment = models.CharField(
        _("environment"), max_length=10, choices=Environment.choices
    )
    next_send_at = models.DateTimeField(
        _("next send not before"), null=True, blank=True
    )
    wait_seconds = models.PositiveIntegerField(
        _("AEAT waiting time (s)"), null=True, blank=True
    )
    last_sent_at = models.DateTimeField(_("last sent at"), null=True, blank=True)

    class Meta:
        verbose_name = _("send control")
        verbose_name_plural = _("send controls")
        ordering = ["issuer_nif", "environment"]
        constraints = [
            models.UniqueConstraint(
                fields=["issuer_nif", "environment"],
                name="verifactu_send_per_issuer_env",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.issuer_nif} ({self.environment})"


class Record(UUIDModel):
    class Type(models.TextChoices):
        ALTA = "alta", pgettext_lazy("verifactu record type", "Registration")
        ANULACION = "anulacion", pgettext_lazy("verifactu record type", "Cancellation")

    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("verifactu status", "Pending")
        SENT = "sent", pgettext_lazy("verifactu status", "Sent, no answer")
        ACCEPTED = "accepted", pgettext_lazy("verifactu status", "Accepted")
        ACCEPTED_WITH_ERRORS = (
            "accepted_with_errors",
            pgettext_lazy("verifactu status", "Accepted with errors"),
        )
        REJECTED = "rejected", pgettext_lazy("verifactu status", "Rejected")

    Environment = Environment
    #: The queue: not in the AEAT yet.
    UNSENT = ("pending", "sent")
    #: Registered by the AEAT.
    IN_AEAT = ("accepted", "accepted_with_errors")

    record_type = models.CharField(_("record type"), max_length=9, choices=Type.choices)
    environment = models.CharField(
        _("environment"), max_length=10, choices=Environment.choices
    )
    issuer_nif = models.CharField(_("issuer tax ID"), max_length=NIF_MAX_LENGTH)
    issuer_name = models.CharField(_("issuer name"), max_length=200)
    sequence = models.PositiveIntegerField(_("sequence"))
    invoice = models.ForeignKey(
        "invoice.Invoice",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("invoice"),
    )
    # The invoice's figures as declared: a copy, never edited.
    invoice_number = models.CharField(_("invoice number"), max_length=NUMBER_MAX_LENGTH)
    issue_date = models.DateField(_("issue date"))
    operation_date = models.DateField(_("operation date"), null=True, blank=True)
    invoice_type = models.CharField(_("invoice type"), max_length=2, blank=True)
    rectification_kind = models.CharField(
        _("rectification kind"), max_length=1, blank=True
    )
    # [{"issuer_nif", "number", "issue_date"}]
    rectified = models.JSONField(
        _("rectified invoices"), default=list, blank=True, encoder=DjangoJSONEncoder
    )
    substituted = models.JSONField(
        _("replaced invoices"), default=list, blank=True, encoder=DjangoJSONEncoder
    )
    description = models.CharField(_("description"), max_length=500, blank=True)
    recipient_name = models.CharField(_("customer name"), max_length=200, blank=True)
    recipient_tax_id = models.CharField(
        _("customer tax ID"), max_length=NIF_MAX_LENGTH, blank=True
    )
    recipient_country = models.CharField(
        _("customer country"), max_length=2, blank=True
    )
    recipient_id_type = models.CharField(
        _("customer document type"), max_length=2, blank=True
    )
    tax_breakdown = models.JSONField(
        _("tax breakdown"), default=list, blank=True, encoder=DjangoJSONEncoder
    )
    base_amount = models.BigIntegerField(_("taxable base"), null=True, blank=True)
    tax_amount = models.BigIntegerField(_("tax"), null=True, blank=True)
    total_amount = models.BigIntegerField(_("total"), null=True, blank=True)
    # Subsanación (VERIFACTU-F24) and the anulación's target (VERIFACTU-F30).
    correction = models.BooleanField(_("correction"), default=False)
    previous_rejection = models.CharField(
        _("previous rejection"), max_length=1, blank=True
    )
    corrects = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
        verbose_name=_("corrects"),
    )
    cancels = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancellations",
        verbose_name=_("cancels"),
    )
    # The chain: what Encadenamiento names (empty fingerprint = the first record of the chain); the previous
    # record when there was one (none after an anchor).
    previous_record = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("previous record"),
    )
    previous_issuer_nif = models.CharField(
        _("previous issuer"), max_length=NIF_MAX_LENGTH, blank=True
    )
    previous_number = models.CharField(
        _("previous invoice"), max_length=NUMBER_MAX_LENGTH, blank=True
    )
    previous_issue_date = models.DateField(
        _("previous invoice date"), null=True, blank=True
    )
    previous_fingerprint = models.CharField(
        _("previous fingerprint"), max_length=FINGERPRINT_LENGTH, blank=True
    )
    # FechaHoraHusoGenRegistro exactly as it entered the fingerprint, and the same moment to sort by.
    generated_at = models.CharField(_("generated at"), max_length=32)
    generated_on = models.DateTimeField(_("generated on"))
    fingerprint = models.CharField(_("fingerprint"), max_length=FINGERPRINT_LENGTH)
    qr_url = models.CharField(_("QR link"), max_length=400)
    # The record element (RegistroAlta / RegistroAnulacion), frozen once built.
    xml = models.TextField(_("XML"), blank=True)
    xml_built_at = models.DateTimeField(_("XML built at"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveIntegerField(_("attempts"), default=0)
    next_attempt_at = models.DateTimeField(_("next attempt"), default=timezone.now)
    wait_reason = models.CharField(_("waiting because"), max_length=40, blank=True)
    wait_detail = models.CharField(_("waiting detail"), max_length=500, blank=True)
    transmitted_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    transmission_id = models.UUIDField(_("transmission ID"), null=True, blank=True)
    envelope_digest = models.CharField(
        _("envelope digest (SHA-256)"), max_length=64, blank=True
    )
    incident = models.BooleanField(_("sent as late (incident)"), default=False)
    csv = models.CharField(_("CSV"), max_length=64, blank=True)
    aeat_code = models.CharField(_("response code"), max_length=16, blank=True)
    aeat_message = models.CharField(_("response message"), max_length=1000, blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("record")
        verbose_name_plural = _("records")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["-created_at", "-id"], name="verifactu_record_recent_idx"
            ),
            models.Index(
                fields=["status", "next_attempt_at"], name="verifactu_record_queue_idx"
            ),
            models.Index(
                fields=["issuer_nif", "environment", "sequence"],
                name="verifactu_record_chain_idx",
            ),
            models.Index(fields=["invoice_number"], name="verifactu_record_number_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["issuer_nif", "environment", "sequence"],
                name="verifactu_record_sequence_in_chain",
            ),
            models.UniqueConstraint(
                fields=["invoice", "environment"],
                condition=Q(record_type="alta", correction=False),
                name="verifactu_record_one_alta_per_invoice",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "pending",
                        "sent",
                        "accepted",
                        "accepted_with_errors",
                        "rejected",
                    ]
                ),
                name="verifactu_record_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(record_type="alta")
                    & Q(
                        base_amount__isnull=False,
                        tax_amount__isnull=False,
                        total_amount__isnull=False,
                    )
                    & ~Q(invoice_type="")
                )
                | (
                    Q(record_type="anulacion")
                    & Q(
                        base_amount__isnull=True,
                        tax_amount__isnull=True,
                        total_amount__isnull=True,
                    )
                ),
                name="verifactu_record_amounts_by_type",
            ),
            models.CheckConstraint(
                condition=Exact(Length("fingerprint"), FINGERPRINT_LENGTH),
                name="verifactu_record_fingerprint_length",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_number} (#{self.sequence}, {self.environment})"



#: The reasons a record waits (VERIFACTU-F17) and those that keep a business from going live (VERIFACTU-F08), by
#: code; ``%(detail)s`` and ``%(at)s`` where they apply.
WAIT_REASONS = {
    "gateway_unavailable": _(
        "ERPlora's sending gateway is not configured on this server"
    ),
    "production_closed": _(
        "ERPlora has not opened real filing with the AEAT on this server yet"
    ),
    "own_certificate_missing": _("your own certificate is not loaded or has expired"),
    "own_certificate_unreadable": _(
        "your own certificate cannot be opened on this server: upload it again"
    ),
    "representation_not_approved": _(
        "ERPlora still has to approve your signed authorisation to file in production"
    ),
    "go_live_forbidden": _(
        "this is a demo business: it always files in the AEAT's test environment"
    ),
    "hub_not_active": _(
        "your ERPlora account has a pending payment or is suspended"
    ),
    "aeat_wait": _("the AEAT asked to wait until %(at)s"),
    "unreachable": _("the gateway or the AEAT could not be reached (%(detail)s)"),
    "refused": _(
        "ERPlora's gateway could not present it (%(detail)s); it is not sent again by itself until the "
        "configuration changes or it is sent by hand"
    ),
    "unknown": _(
        "the submission left and no answer came back; it is sent again, declared as late"
    ),
    "aeat_fault": _(
        "the AEAT refused the whole submission and it is tried again (%(detail)s)"
    ),
    "xml_invalid": _("its XML does not pass the AEAT's schema (%(detail)s)"),
}


#: What a refusal of the gateway means, by its code (saas#29), shown in place of the SaaS's own English message.
GATEWAY_REFUSALS = {
    "hub_unknown": _(
        "ERPlora does not recognise this business: contact ERPlora's support"
    ),
    "representation_not_approved": WAIT_REASONS["representation_not_approved"],
}


def gateway_refusal_text(detail: str) -> str:
    """A refusal's ``code: message`` in the active language when its code is known; else as the gateway said it."""
    known = GATEWAY_REFUSALS.get(detail.split(":", 1)[0].strip())
    return detail if known is None else str(known)


def wait_reason_text(code: str, detail: str = "", at: str = "") -> str:
    """The reason ``code`` in the active language."""
    template = WAIT_REASONS.get(code)
    if template is None:
        return code
    if code == "refused":
        detail = gateway_refusal_text(detail)
    return str(template) % {"detail": detail, "at": at}


class Event(UUIDModel):
    class Kind(models.TextChoices):
        RECORD_CREATED = "record_created", _("Record created")
        DEFERRED = "deferred", _("Submission postponed")
        ACCEPTED = "accepted", _("Submission accepted")
        ACCEPTED_WITH_ERRORS = "accepted_with_errors", _("Accepted with errors")
        FAILED = "failed", _("Submission failed")
        QUEUE_PROCESSED = "queue_processed", _("Queue processed")
        QUEUE_RETRIED = "queue_retried", _("Record rescheduled")
        CHAIN_VALID = "chain_valid", _("Chain verified")
        CHAIN_BROKEN = "chain_broken", _("Chain broken")
        AEAT_QUERIED = "aeat_queried", _("AEAT query")
        CHAIN_RECOVERED = "chain_recovered", _("Chain recovered")
        CONNECTION_TEST = "connection_test", _("Connection test")
        CONFIG_CHANGED = "config_changed", _("Configuration changed")

    class Severity(models.TextChoices):
        DEBUG = "debug", _("Debug")
        INFO = "info", _("Info")
        WARNING = "warning", _("Warning")
        ERROR = "error", _("Error")
        CRITICAL = "critical", _("Critical")

    kind = models.CharField(_("type"), max_length=24, choices=Kind.choices)
    severity = models.CharField(
        _("severity"), max_length=8, choices=Severity.choices, default=Severity.INFO
    )
    message_key = models.CharField(_("message key"), max_length=48)
    params = models.JSONField(
        _("parameters"), default=dict, blank=True, encoder=DjangoJSONEncoder
    )
    record = models.ForeignKey(
        Record,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="events",
        verbose_name=_("record"),
    )
    environment = models.CharField(_("environment"), max_length=10, blank=True)
    # The sentence in English and in Spanish, lower case: what «Search type or message…» looks in.
    search_text = models.TextField(_("search text"), blank=True)
    created_at = models.DateTimeField(_("when"), default=timezone.now)
    actor = models.CharField(_("actor"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["-created_at", "-id"], name="verifactu_event_recent_idx"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.created_at:%Y-%m-%d %H:%M}"

    def message(self) -> str:
        """The sentence in the active language."""
        template = EVENT_MESSAGES.get(self.message_key)
        if template is None:
            return self.message_key
        params = dict(self.params or {})
        if "environment" in params:
            params["environment"] = str(
                dict(Environment.choices).get(
                    params["environment"], params["environment"]
                )
            )
        if "status" in params:
            params["status_label"] = str(
                dict(Record.Status.choices).get(params["status"], params["status"])
            )
        if "reason" in params:
            params["why"] = wait_reason_text(
                params["reason"], params.get("detail", ""), params.get("at", "")
            )
        try:
            return str(template) % params
        except (KeyError, TypeError, ValueError):
            return str(template)

    def compose_search_text(self) -> str:
        """The sentence in both languages, lower case."""
        texts = []
        for language in ("en", "es"):
            with translation.override(language):
                texts.append(f"{self.get_kind_display()} {self.message()}")
        return " ".join(texts).lower()


#: The sentences of the audit trail, by key.
EVENT_MESSAGES = {
    "alta_sealed": _(
        "Registration record #%(sequence)s sealed for invoice %(invoice_number)s."
    ),
    "correction_sealed": _(
        "Correction record #%(sequence)s sealed for invoice %(invoice_number)s."
    ),
    "anulacion_sealed": _(
        "Cancellation record #%(sequence)s sealed for invoice %(invoice_number)s: %(reason_text)s"
    ),
    "deferred": _("Not sent to the AEAT yet (%(count)s record(s)): %(why)s."),
    "accepted": _("AEAT (%(environment)s): %(count)s record(s) accepted, CSV %(csv)s."),
    "accepted_with_errors": _(
        "Invoice %(invoice_number)s accepted with errors by the AEAT (%(code)s): %(message)s"
    ),
    "rejected": _(
        "Invoice %(invoice_number)s rejected by the AEAT (%(code)s): %(message)s"
    ),
    "queue_processed": _(
        "Queue processed: %(sent)s sent, %(accepted)s accepted, %(rejected)s rejected, %(waiting)s waiting."
    ),
    "queue_retried": _("Invoice %(invoice_number)s goes out with the next pass."),
    "record_reconciled": _(
        "Invoice %(invoice_number)s was already in the AEAT (%(status_label)s): out of the queue."
    ),
    "chain_valid": _(
        "Fingerprint chain intact: %(total)s record(s) with their SHA-256 chaining verified (%(issuer_nif)s). "
        "Amounts are not re-audited."
    ),
    "chain_broken": _(
        "Fingerprint chain BROKEN at sequence %(first_invalid_sequence)s (%(issuer_nif)s)."
    ),
    "aeat_queried": _("AEAT query: %(count)s record(s) retrieved for %(issuer_nif)s."),
    "chain_recovered_from_aeat": _(
        "Chain recovered from the AEAT for %(issuer_nif)s: it continues after invoice %(invoice_number)s "
        "(%(found)s record(s) found)."
    ),
    "chain_continued_manually": _(
        "Chain continued manually for %(issuer_nif)s after invoice %(invoice_number)s."
    ),
    "connection_ok": _("Connection test (%(environment)s): this business can send."),
    "connection_blocked": _(
        "Connection test (%(environment)s): it cannot send yet: %(why)s."
    ),
    "certificate_uploaded": _(
        "Own certificate of %(holder)s (%(holder_tax_id)s) uploaded; it expires on %(expires_on)s."
    ),
    "certificate_removed": _(
        "Own certificate of %(holder)s (%(holder_tax_id)s) removed."
    ),
    "route_own": _("From now on you send with your own certificate."),
    "route_erplora": _("From now on ERPlora files on your behalf."),
    "went_live": _("The business went live: records go to the real AEAT."),
    "back_to_testing": _("The business went back to the AEAT's test environment."),
    "account_synced": _(
        "Data received from your ERPlora account (version %(version)s)."
    ),
    "representation_submitted": _(
        "Representation authorisation no. %(version)s sent to ERPlora for review."
    ),
    "representation_under_review": _(
        "ERPlora is reviewing the representation authorisation."
    ),
    "representation_approved": _(
        "ERPlora approved the representation authorisation: it can file on your behalf."
    ),
    "representation_returned": _(
        "ERPlora returned the representation authorisation: %(note)s"
    ),
    "representation_revoked": _("The representation authorisation was revoked."),
    "representation_none": _(
        "ERPlora holds no signed representation authorisation for this business."
    ),
    "xml_invalid": _(
        "Invoice %(invoice_number)s cannot be sent: its XML does not pass the AEAT's schema (%(detail)s)."
    ),
}


class AeatRecord(UUIDModel):
    """A record as the AEAT's last query returned it."""

    issuer_nif = models.CharField(_("issuer tax ID"), max_length=NIF_MAX_LENGTH)
    environment = models.CharField(
        _("environment"), max_length=10, choices=Environment.choices
    )
    invoice_number = models.CharField(_("invoice number"), max_length=NUMBER_MAX_LENGTH)
    issue_date = models.DateField(_("issue date"), null=True, blank=True)
    fingerprint = models.CharField(
        _("fingerprint"), max_length=FINGERPRINT_LENGTH, blank=True
    )
    state = models.CharField(_("status"), max_length=40, blank=True)
    csv = models.CharField(_("CSV"), max_length=64, blank=True)
    generated_on = models.DateTimeField(_("generated on"), null=True, blank=True)
    queried_at = models.DateTimeField(_("queried at"), default=timezone.now)

    class Meta:
        verbose_name = _("record at the AEAT")
        verbose_name_plural = _("records at the AEAT")
        ordering = ["-generated_on", "-id"]

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.issuer_nif})"

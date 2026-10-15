"""Models of the payment app: the accounts the business pays from, its outgoing payments and the
counter that numbers them by day.

- ``PaymentMethod`` is where the money leaves from (a bank account, the company card, the cash
  drawer), never how a customer pays: that is the sale app's ``PaymentMethod``. It is deactivated,
  never deleted, and its name is unique whatever the case (the assistant names it).
- ``Payment`` is one outgoing payment, in the minor unit of its currency (> 0), with its reference
  ``PAY-YYYYMMDD-NNNN`` and its ladder: draft → approved → sent → completed, or cancelled.
- ``PaymentCounter`` holds the last number given on a business day; services.py raises it with
  ``UPDATE … RETURNING`` in the transaction of the payment (never a sequence).

Phase 1 has no tenancy (like ``apps.demo``): phase 2 moves these tables to each hub's database.
"""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
NAME_MAX_LENGTH = 100
BENEFICIARY_MAX_LENGTH = 200
#: The longest IBAN (ISO 13616) is 34 characters.
IBAN_MAX_LENGTH = 34
REFERENCE_MAX_LENGTH = 32
INVOICE_REF_MAX_LENGTH = 100


class PaymentMethod(UUIDModel):
    class Type(models.TextChoices):
        CASH = "cash", pgettext_lazy("payment method type", "Cash")
        TRANSFER = "transfer", pgettext_lazy("payment method type", "Bank transfer")
        CARD = "card", pgettext_lazy("payment method type", "Card")
        SEPA = "sepa", pgettext_lazy("payment method type", "SEPA")
        CHECK = "check", pgettext_lazy("payment method type", "Cheque")
        OTHER = "other", pgettext_lazy("payment method type", "Other")

    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    method_type = models.CharField(
        _("type"), max_length=16, choices=Type.choices, default=Type.TRANSFER
    )
    bank_account_ref = models.CharField(
        _("account"), max_length=NAME_MAX_LENGTH, blank=True
    )
    is_active = models.BooleanField(pgettext_lazy("payment", "active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("changed by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = pgettext_lazy("payment", "payment method")
        verbose_name_plural = pgettext_lazy("payment", "payment methods")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="payment_method_name_unique"),
        ]

    def __str__(self) -> str:
        return self.name


class PaymentStatus(models.TextChoices):
    """The ladder of a payment (``Payment.Status``); out here so the model's constraint can read it."""

    DRAFT = "draft", pgettext_lazy("payment status", "Draft")
    APPROVED = "approved", pgettext_lazy("payment status", "Approved")
    SENT = "sent", pgettext_lazy("payment status", "Sent")
    COMPLETED = "completed", pgettext_lazy("payment status", "Completed")
    CANCELLED = "cancelled", pgettext_lazy("payment status", "Cancelled")


class Payment(UUIDModel):
    Status = PaymentStatus

    reference = models.CharField(
        _("reference"), max_length=REFERENCE_MAX_LENGTH, unique=True
    )
    method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=pgettext_lazy("payment", "method"),
    )
    payment_date = models.DateField(_("payment date"))
    # In the minor unit of ``currency`` (cents in euros), always above 0.
    amount = models.BigIntegerField(_("amount"))
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    beneficiary_name = models.CharField(
        _("beneficiary"), max_length=BENEFICIARY_MAX_LENGTH
    )
    beneficiary_iban = models.CharField(
        _("beneficiary IBAN"), max_length=IBAN_MAX_LENGTH, blank=True
    )
    concept = models.TextField(_("concept"), blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    supplier_invoice_ref = models.CharField(
        _("supplier invoice"), max_length=INVOICE_REF_MAX_LENGTH, blank=True
    )
    cancel_reason = models.TextField(_("cancellation reason"), blank=True)
    # The trail of the ladder: who approved (``updated_by`` is only whoever moved it last) and when
    # each step happened, set by the step itself.
    approved_by = models.CharField(
        pgettext_lazy("payment", "approved by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    approved_at = models.DateTimeField(pgettext_lazy("payment", "approved at"), null=True, blank=True)
    sent_at = models.DateTimeField(pgettext_lazy("payment", "sent at"), null=True, blank=True)
    completed_at = models.DateTimeField(pgettext_lazy("payment", "completed at"), null=True, blank=True)
    cancelled_by = models.CharField(
        pgettext_lazy("payment", "cancelled by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    cancelled_at = models.DateTimeField(pgettext_lazy("payment", "cancelled at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("changed by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["status"], name="payment_status_idx"),
            models.Index(fields=["payment_date"], name="payment_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="payment_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(status__in=PaymentStatus.values),
                name="payment_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.reference


class PaymentCounter(UUIDModel):
    """The last reference number given on a business day."""

    day = models.DateField(_("business day"), unique=True)
    last = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("payment counter")
        verbose_name_plural = _("payment counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day}: {self.last}"

"""The log of the emails of an invoice. Sending one changes nothing of the document."""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

ADDRESS_MAX_LENGTH = 254


class InvoiceEmail(UUIDModel):
    """One email of an invoice: to whom, when and how it ended."""

    class Status(models.TextChoices):
        QUEUED = "queued", pgettext_lazy("invoice email", "Waiting to be sent")
        SENDING = "sending", pgettext_lazy("invoice email", "Sending")
        SENT = "sent", pgettext_lazy("invoice email", "Sent")
        FAILED = "failed", pgettext_lazy("invoice email", "Not sent")

    invoice = models.ForeignKey(
        "invoice.Invoice", on_delete=models.CASCADE, related_name="emails", verbose_name=_("invoice")
    )
    # Empty once the personal data of its customer is erased.
    to_address = models.EmailField(
        pgettext_lazy("invoice email", "to"), max_length=ADDRESS_MAX_LENGTH, blank=True
    )
    status = models.CharField(
        pgettext_lazy("invoice email", "status"), max_length=8, choices=Status.choices, default=Status.QUEUED
    )
    status_at = models.DateTimeField(pgettext_lazy("invoice email", "status since"), default=timezone.now)
    sent_at = models.DateTimeField(pgettext_lazy("invoice email", "sent at"), null=True, blank=True)
    # Why it was not sent; empty otherwise.
    error_code = models.CharField(pgettext_lazy("invoice email", "error code"), max_length=60, blank=True)
    # The caller's own key of the request: asking again with it sends nothing more.
    attempt_key = models.UUIDField(
        pgettext_lazy("invoice email", "request key"), null=True, blank=True, unique=True
    )
    requested_at = models.DateTimeField(pgettext_lazy("invoice email", "requested at"), default=timezone.now)
    requested_by = models.CharField(
        pgettext_lazy("invoice email", "requested by"), max_length=128, blank=True
    )

    class Meta:
        verbose_name = _("email of an invoice")
        verbose_name_plural = _("emails of invoices")
        ordering = ["-requested_at", "-id"]
        indexes = [
            # What the worker looks for every few minutes.
            models.Index(
                fields=["status_at"], condition=Q(status__in=("queued", "sending")), name="invoice_email_on_its_way_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.status} {self.id}"

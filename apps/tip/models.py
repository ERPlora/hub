"""The tips of the business and its tip settings. A tip is a row of its own tied to its sale: never part of the sale's
total, its tax or its fiscal record."""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.cash_register.models import Session
from apps.sale.models.payment_methods import PaymentMethod
from apps.sale.models.sales import Sale
from apps.staff.models import Member
from base.models.access import ACTOR_MAX_LENGTH


def _actor(label) -> models.CharField:
    return models.CharField(label, max_length=ACTOR_MAX_LENGTH, blank=True)


class Settings(UUIDModel):
    """The tip settings of the business: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    enabled = models.BooleanField(_("ask for a tip at the charge"), default=False)
    allow_custom = models.BooleanField(_("allow another amount"), default=True)
    # Which of the three suggestions comes chosen (1 to 3); 0: «No tip».
    preselected = models.PositiveSmallIntegerField(_("chosen suggestion"), default=0)
    # Payment method id → its three suggestions, each {"percent": …, "amount": …} with one of the two; a method left out
    # takes the factory ones.
    suggestions = models.JSONField(_("suggestions by payment method"), default=dict, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = _actor(_("updated by"))

    class Meta:
        verbose_name = _("tip settings")
        verbose_name_plural = _("tip settings")
        constraints = [models.UniqueConstraint(fields=["singleton"], name="tip_settings_single_row")]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class Tip(UUIDModel):
    """A tip: of a sale (and of whoever it belongs to) or, without a sale nor a person, to the pool."""

    class Status(models.TextChoices):
        ACTIVE = "active", pgettext_lazy("tip status", "Active")
        VOIDED = "voided", pgettext_lazy("tip status", "Voided")

    sale = models.ForeignKey(
        Sale, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("sale")
    )
    member = models.ForeignKey(
        Member, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("for")
    )
    method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name="+", verbose_name=_("payment method")
    )
    method_name = models.CharField(_("payment method name"), max_length=60)
    method_type = models.CharField(_("payment method type"), max_length=16, choices=PaymentMethod.Type.choices)
    amount = models.PositiveBigIntegerField(_("amount"))
    status = models.CharField(_("status"), max_length=8, choices=Status.choices, default=Status.ACTIVE)
    # The drawer session it entered; empty: it entered none (the drawer off, or closed for a tip not in cash).
    session = models.ForeignKey(
        Session, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name=_("cash session")
    )
    # The charge's attempt key (with its leg), so a retry never records the tip twice.
    attempt_key = models.CharField(_("attempt key"), max_length=128, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    created_by = _actor(_("created by"))
    adjusted_at = models.DateTimeField(_("adjusted at"), null=True, blank=True)
    adjusted_by = _actor(_("adjusted by"))
    adjust_reason = models.CharField(_("reason of the adjustment"), max_length=255, blank=True)
    voided_at = models.DateTimeField(_("voided at"), null=True, blank=True)
    voided_by = _actor(_("voided by"))
    void_reason = models.CharField(_("reason of the void"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("tip")
        verbose_name_plural = _("tips")
        # The order of tip.tip.list: newest first, id as the tie-break.
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["-created_at", "id"], name="tip_tip_created_idx")]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="tip_tip_amount_positive")]

    def __str__(self) -> str:
        return f"{self.method_name} {self.amount}"

    @property
    def pool(self) -> bool:
        return self.sale_id is None

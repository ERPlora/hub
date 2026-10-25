"""Models of the cash register app.

- ``Settings`` (one row at most; without it the factory values apply) says how the drawer works.
- ``Register`` is a physical drawer (never deleted: sessions name it).
- ``Session`` is a shift of the drawer: its number of the business day, the opening float and, once
  closed, the expected cash, the counted one and their difference, frozen for good. One open at a time.
- ``SessionCounter`` numbers the sessions of a business day (``UPDATE … RETURNING``, never a sequence).
- ``Movement`` is a line of a session: cash brought in or taken out by hand and, once the session is
  closed, the copy of the sale lines of the shift (charges, voids and refunds of sale), each copied once.
- ``Count`` is a count of the drawer by notes and coins (or its total).

Money is in whole cents and a stored amount is never negative: its sign comes from its type.
"""

import datetime as dt

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.sale.models import PaymentMethod

ACTOR_MAX_LENGTH = 128
NUMBER_WIDTH = 4
#: The factory hour of the daily auto-close (Toast's business-day cut-off).
AUTO_CLOSE_TIME = dt.time(4, 0)


def default_auto_close_time() -> dt.time:
    """The field default as a callable: a fixed time trips ``fields.W161`` within 10 s of that hour (UTC)."""
    return AUTO_CLOSE_TIME


def session_number(day: dt.date, sequence: int) -> str:
    """``S-AAMMDD-NNNN``: four digits as a minimum width, never a ceiling."""
    return f"S-{day:%y%m%d}-{sequence:0{NUMBER_WIDTH}d}"


class Settings(UUIDModel):
    """The drawer settings of the business: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    enable_cash_register = models.BooleanField(_("cash register on"), default=True)
    require_opening_balance = models.BooleanField(
        _("require an opening float"), default=False
    )
    require_closing_balance = models.BooleanField(
        _("require a count to close"), default=True
    )
    allow_negative_balance = models.BooleanField(
        _("allow a negative balance"), default=False
    )
    require_blind_count = models.BooleanField(_("blind count"), default=False)
    auto_close_enabled = models.BooleanField(_("daily auto-close"), default=False)
    auto_close_time = models.TimeField(
        _("auto-close time"), default=default_auto_close_time
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("drawer settings")
        verbose_name_plural = _("drawer settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="cash_register_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="cash_register_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(auto_close_time__minute=0, auto_close_time__second=0),
                name="cash_register_settings_whole_hour",
            ),
        ]

    def __str__(self) -> str:
        return str(_("drawer settings"))


class Register(UUIDModel):
    """A physical drawer of the business."""

    name = models.CharField(_("name"), max_length=100)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("drawer")
        verbose_name_plural = _("drawers")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), name="cash_register_register_name_unique"
            ),
            models.CheckConstraint(
                condition=~Q(name=""), name="cash_register_register_name_given"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class SessionCounter(UUIDModel):
    """The last session number given on a business day."""

    day = models.DateField(_("business day"), unique=True)
    last = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("session counter")
        verbose_name_plural = _("session counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day}: {self.last}"


class Session(UUIDModel):
    """A shift of the drawer. Once closed it never changes: corrections go to the open one."""

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        CLOSED = "closed", _("Closed")

    number = models.CharField(_("number"), max_length=24, unique=True)
    business_day = models.DateField(_("business day"))
    sequence = models.PositiveIntegerField(_("number of the day"))
    register = models.ForeignKey(
        Register,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name=_("drawer"),
    )
    status = models.CharField(
        _("status"), max_length=8, choices=Status.choices, default=Status.OPEN
    )
    opened_at = models.DateTimeField(_("opened at"), default=timezone.now)
    opened_by = models.CharField(
        _("opened by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    opening_balance = models.BigIntegerField(_("opening float"), default=0)
    opening_notes = models.TextField(_("opening notes"), blank=True)
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    closed_by = models.CharField(
        _("closed by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    closing_balance = models.BigIntegerField(_("counted cash"), null=True, blank=True)
    expected_balance = models.BigIntegerField(_("expected cash"), null=True, blank=True)
    difference = models.BigIntegerField(_("difference"), null=True, blank=True)
    closing_notes = models.TextField(_("closing notes"), blank=True)
    auto_closed = models.BooleanField(_("closed by itself"), default=False)

    class Meta:
        verbose_name = _("cash session")
        verbose_name_plural = _("cash sessions")
        ordering = ["-opened_at", "-id"]
        indexes = [
            models.Index(fields=["-opened_at", "-id"], name="cash_register_recent_idx"),
            models.Index(
                fields=["business_day", "sequence"], name="cash_register_day_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["status"],
                condition=Q(status="open"),
                name="cash_register_one_open_session",
            ),
            models.CheckConstraint(
                condition=Q(opening_balance__gte=0),
                name="cash_register_session_float_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(closing_balance__isnull=True) | Q(closing_balance__gte=0),
                name="cash_register_session_count_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(
                    status="open",
                    closed_at__isnull=True,
                    expected_balance__isnull=True,
                    closing_balance__isnull=True,
                    difference__isnull=True,
                )
                | Q(
                    status="closed",
                    closed_at__isnull=False,
                    expected_balance__isnull=False,
                ),
                name="cash_register_session_close_is_whole",
            ),
            models.CheckConstraint(
                condition=Q(closing_balance__isnull=True, difference__isnull=True)
                | Q(
                    closing_balance__isnull=False,
                    difference=F("closing_balance") - F("expected_balance"),
                ),
                name="cash_register_session_difference",
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN


class Movement(UUIDModel):
    """A line of a session. ``in``/``out`` are written by hand; ``sale``, ``void`` and ``refund`` are the
    copy of sale's own lines, made when the session closes (or never, while it is open: they are read)."""

    class Type(models.TextChoices):
        IN = "in", _("Cash in")
        OUT = "out", _("Cash out")
        SALE = "sale", _("Sale")
        REFUND = "refund", _("Refund")
        VOID = "void", _("Void")

    #: The types that take money out of the drawer.
    OUTFLOWS = (Type.OUT, Type.REFUND, Type.VOID)
    #: The types a person records by hand.
    MANUAL = (Type.IN, Type.OUT)

    session = models.ForeignKey(
        Session,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements",
        verbose_name=_("session"),
    )
    type = models.CharField(_("type"), max_length=8, choices=Type.choices)
    amount = models.BigIntegerField(_("amount"))
    method_type = models.CharField(
        _("payment method type"),
        max_length=16,
        choices=PaymentMethod.Type.choices,
        default=PaymentMethod.Type.CASH,
    )
    method_name = models.CharField(_("payment method"), max_length=60, blank=True)
    description = models.CharField(_("concept"), max_length=255, blank=True)
    sale = models.ForeignKey(
        "sale.Sale",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("sale"),
    )
    sale_number = models.CharField(_("sale number"), max_length=24, blank=True)
    document_type = models.CharField(_("document"), max_length=8, blank=True)
    sale_payment = models.ForeignKey(
        "sale.SalePayment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("sale payment"),
    )
    refund_payment = models.ForeignKey(
        "sale.RefundPayment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("refund payment"),
    )
    gift_total = models.BigIntegerField(_("comps at cost"), default=0)
    created_at = models.DateTimeField(_("when"), default=timezone.now)
    created_by = models.CharField(_("by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("cash movement")
        verbose_name_plural = _("cash movements")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["session", "-created_at"], name="cash_register_mov_session_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0, gift_total__gte=0),
                name="cash_register_movement_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(type__in=["sale", "refund", "void"])
                | Q(session__isnull=False, amount__gt=0, sale__isnull=True),
                name="cash_register_movement_manual_in_a_session",
            ),
            models.CheckConstraint(
                condition=~Q(type__in=["sale", "void"]) | Q(sale__isnull=False),
                name="cash_register_movement_sale_named",
            ),
            models.CheckConstraint(
                condition=~Q(type="refund") | Q(refund_payment__isnull=False),
                name="cash_register_movement_refund_named",
            ),
            # Each line of sale is copied once: a tender as a sale and once more as its void, a refund
            # leg once, and a sale without tenders (all comps) once.
            models.UniqueConstraint(
                fields=["sale_payment", "type"],
                condition=Q(sale_payment__isnull=False),
                name="cash_register_movement_payment_once",
            ),
            models.UniqueConstraint(
                fields=["refund_payment"],
                condition=Q(refund_payment__isnull=False),
                name="cash_register_movement_refund_once",
            ),
            models.UniqueConstraint(
                fields=["sale"],
                condition=Q(type="sale", sale_payment__isnull=True),
                name="cash_register_movement_comps_once",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.amount}"

    @property
    def signed_amount(self) -> int:
        """In and sales add to the drawer; out, refunds and voids take from it."""
        return -self.amount if self.type in self.OUTFLOWS else self.amount


class Count(UUIDModel):
    """A count of the drawer, by notes and coins or as a total."""

    class Type(models.TextChoices):
        OPENING = "opening", _("Opening")
        CLOSING = "closing", _("Closing")

    session = models.ForeignKey(
        Session,
        on_delete=models.PROTECT,
        related_name="counts",
        verbose_name=_("session"),
    )
    type = models.CharField(
        _("count type"), max_length=8, choices=Type.choices, default=Type.CLOSING
    )
    # ``{"bills": {"50": 2}, "coins": {"0.50": 3}}``: face value in major units → pieces.
    denominations = models.JSONField(
        _("notes and coins"), default=dict, blank=True, encoder=DjangoJSONEncoder
    )
    total = models.BigIntegerField(_("total counted"))
    notes = models.CharField(_("notes"), max_length=500, blank=True)
    counted_at = models.DateTimeField(_("counted at"), default=timezone.now)
    counted_by = models.CharField(
        _("counted by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("cash count")
        verbose_name_plural = _("cash counts")
        ordering = ["-counted_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gte=0), name="cash_register_count_not_negative"
            )
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.total}"

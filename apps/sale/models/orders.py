"""The open checks and their lines."""

from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.sale.models.departments import Department
from apps.sale.models.fields import PERCENT, QUANTITY, _actor, _json_list, _percent_range


class Order(UUIDModel):
    """An open check: mutable, its amounts provisional; charging it creates one or more sales."""

    class Status(models.TextChoices):
        # Own context: an open check («cuenta») is «Abierta», not Demo's «Abierto» of the same English.
        OPEN = "open", pgettext_lazy("sale", "Open")
        COMPLETED = "completed", _("Completed")
        VOIDED = "voided", _("Voided")

    class Source(models.TextChoices):
        POS = "pos", _("Till")
        COUNTER = "counter", _("Counter sale")

    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.OPEN)
    source = models.CharField(_("source"), max_length=10, choices=Source.choices, default=Source.POS)
    label = models.CharField(_("title"), max_length=120, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    appointment_id = models.UUIDField(_("appointment"), null=True, blank=True)
    # Who serves the check (a member of Staff, with the name it had when chosen); empty = whoever holds the session.
    staff_id = models.UUIDField(_("served by"), null=True, blank=True)
    staff_name = models.CharField(_("server's name"), max_length=201, blank=True, default="", db_default="")
    discount_percent = models.DecimalField(_("discount (%)"), default=Decimal("0"), **PERCENT)
    # In whole minor units of the business's currency (not always the cent): its name never says the unit.
    discount_amount = models.PositiveBigIntegerField(_("fixed-amount discount"), default=0)
    discount_approved_by = _actor(_("discount approved by"))
    # Σ of the live unpaid lines' totals, before the ticket discount: what the till paints, never fiscal.
    provisional_total = models.BigIntegerField(_("provisional total"), default=0)
    version = models.PositiveIntegerField(_("version"), default=1)
    # A counter sale's check claims its charge attempt: the same attempt at once waits on this unique
    # key and then answers the sale the first one charged.
    attempt_key = models.CharField(
        _("attempt key"), max_length=128, unique=True, null=True, blank=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = _actor(_("created by"))
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    # Its bill's first print for the table: while the check is open, Tables paints its table «Bill requested».
    bill_printed_at = models.DateTimeField(_("bill printed at"), null=True, blank=True)
    voided_by = _actor(_("voided by"))
    # A check joined with another (SALE-F24) ends voided and names the one that stays: a till that had it on
    # screen follows that one instead of saying it was closed on another device.
    merged_into_id = models.UUIDField(
        _("joined with"), null=True, blank=True, editable=False
    )

    class Meta:
        verbose_name = _("open check")
        verbose_name_plural = _("open checks")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="sale_order_status_idx")
        ]
        constraints = [
            _percent_range("sale_order_discount_range"),
            # An appointment has one open check at a time: two «Charge» of it never charge it twice.
            models.UniqueConstraint(
                fields=["appointment_id"],
                condition=Q(status="open", source="pos", appointment_id__isnull=False),
                name="sale_order_one_open_per_appointment",
            ),
        ]

    def __str__(self) -> str:
        return self.label or str(self.id)


class OrderLineQuerySet(models.QuerySet):
    def live(self) -> "OrderLineQuerySet":
        """Not removed nor voided."""
        return self.filter(removed_at__isnull=True)

    def unpaid(self) -> "OrderLineQuerySet":
        """Not charged by any sale yet."""
        return self.filter(sale__isnull=True)


class OrderLine(UUIDModel):
    """A working row of an open check: its price, unit and tax category are frozen when it is added."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("open check"),
    )
    position = models.PositiveIntegerField(_("position"))
    product_id = models.UUIDField(_("product"), null=True, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("department"),
    )
    name = models.CharField(_("name"), max_length=200)
    sku = models.CharField(_("SKU"), max_length=64, blank=True)
    is_service = models.BooleanField(_("service"), default=False)
    category_id = models.UUIDField(_("product category"), null=True, blank=True)
    # The unit of the quantity and the one the price refers to, frozen with their exact factor.
    unit = models.CharField(_("unit"), max_length=8, default="ud")
    unit_factor_num = models.PositiveBigIntegerField(default=1)
    unit_factor_den = models.PositiveBigIntegerField(default=1)
    increment = models.DecimalField(_("step"), default=Decimal("1"), **QUANTITY)
    price_quantity = models.DecimalField(
        _("price quantity"), default=Decimal("1"), **QUANTITY
    )
    pricing_unit = models.CharField(_("pricing unit"), max_length=8, default="ud")
    pricing_factor_num = models.PositiveBigIntegerField(default=1)
    pricing_factor_den = models.PositiveBigIntegerField(default=1)
    quantity = models.DecimalField(_("quantity"), **QUANTITY)
    unit_price = models.PositiveBigIntegerField(_("price"))
    cost = models.PositiveBigIntegerField(_("cost"), default=0)
    tax_category_key = models.CharField(_("tax category"), max_length=80)
    discount_percent = models.DecimalField(
        _("discount (%)"), default=Decimal("0"), **PERCENT
    )
    discount_approved_by = _actor(_("discount approved by"))
    is_gift = models.BooleanField(_("comp"), default=False)
    gift_reason = models.CharField(_("comp reason"), max_length=200, blank=True)
    notes = models.CharField(_("note"), max_length=255, blank=True)
    staff_id = models.UUIDField(_("served by"), null=True, blank=True)
    # A service of the Services app (an opaque id: Services is no requirement, as Inventory).
    service_id = models.UUIDField(_("service id"), null=True, blank=True)
    # The voucher session of the Services app that pays the line (SALE-F27): its id and its voucher's,
    # the voucher's name and the sessions it had left when applied, and when the hold runs out.
    voucher_session_id = models.UUIDField(_("voucher session"), null=True, blank=True)
    voucher_grant_id = models.UUIDField(_("voucher"), null=True, blank=True)
    voucher_name = models.CharField(_("voucher name"), max_length=200, blank=True)
    voucher_remaining = models.IntegerField(
        _("sessions left on the voucher"), null=True, blank=True
    )
    voucher_hold_until = models.DateTimeField(
        _("voucher session held until"), null=True, blank=True
    )
    # The options of Modifiers chosen for the line (SALE-F11), frozen as Modifiers valued them when it was
    # ordered: ``modifiers`` every pick in the order chosen (``unit_price`` already adds the ones taxed as the
    # dish), ``modifier_lines`` the ones of another tax category, charged on a child line of their own (their
    # ``quantity`` is per unit of the dish), ``kitchen_text`` what the kitchen reads under the dish. Own context, here
    # and on the charged line: they are its «suplementos», not Clientes' «opciones» of the same English.
    modifiers = _json_list(pgettext_lazy("sale", "options"))
    modifier_lines = _json_list(_("options on a line of their own"))
    kitchen_text = models.CharField(
        _("kitchen text"), max_length=500, blank=True, default="", db_default=""
    )
    # A menu of Menus (SALE-F12): its id and what Menus answered when it was ordered (COMBO-F08) —
    # ``choices`` as picked, ``kitchen_name``, ``supply_kind``, ``split``, ``tax_category_key`` and the
    # ``components`` in order. ``unit_price`` is the amount ordered; charging asks Menus again with it.
    combo_id = models.UUIDField(_("menu"), null=True, blank=True)
    combo = models.JSONField(
        _("menu as ordered"), default=dict, blank=True, db_default={}, encoder=DjangoJSONEncoder
    )
    # The allergens of its product and of its options (``base.allergens`` codes, in the order of the list), frozen when
    # it is ordered as its options are; a menu has none of its own: each dish of ``combo`` keeps its product's.
    allergens = _json_list(_("allergens"))
    # The customer's allergy the waiter marks before the line is sent (SALE-F41), ``base.allergens`` codes.
    allergy = _json_list(_("customer's allergy"))
    line_total = models.BigIntegerField(_("line total"), default=0)
    round_no = models.PositiveIntegerField(_("round"), default=0)
    fired_at = models.DateTimeField(_("sent to the kitchen at"), null=True, blank=True)
    sale = models.ForeignKey(
        "Sale",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_lines",
        verbose_name=_("sale"),
    )
    removed_at = models.DateTimeField(_("removed at"), null=True, blank=True)
    void_reason = models.CharField(_("void reason"), max_length=255, blank=True)
    voided_by = _actor(_("voided by"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = _actor(_("created by"))

    objects = OrderLineQuerySet.as_manager()

    class Meta:
        verbose_name = _("open check line")
        verbose_name_plural = _("open check lines")
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["order", "position"], name="sale_orderline_order_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="sale_orderline_quantity_positive"
            ),
            _percent_range("sale_orderline_discount_range"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.name}"

    @property
    def is_live(self) -> bool:
        return self.removed_at is None

    @property
    def is_fired(self) -> bool:
        return self.fired_at is not None

    @property
    def paid_by_voucher(self) -> bool:
        return self.voucher_session_id is not None

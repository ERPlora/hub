"""The kitchen tickets and their dishes."""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.kitchen.models.fields import (
    ACTOR_MAX_LENGTH,
    Audited,
    Destination,
    OrderType,
    PrinterUsage,
    _destination,
    _in,
    _printer_usage,
)
from apps.kitchen.models.stations import Station

QUANTITY = {"max_digits": 12, "decimal_places": 3}


class Priority(models.TextChoices):
    NORMAL = "normal", _("Normal")
    RUSH = "rush", _("Rush")
    VIP = "vip", _("VIP")


class TicketStatus(models.TextChoices):
    PENDING = "pending", _("To prepare")
    PREPARING = "preparing", _("Preparing")
    READY = "ready", _("Ready")
    SERVED = "served", _("Served")
    CANCELLED = "cancelled", _("Cancelled")


class ItemStatus(models.TextChoices):
    PENDING = "pending", _("To prepare")
    PREPARING = "preparing", _("Preparing")
    READY = "ready", _("Ready")
    SERVED = "served", _("Served")
    CANCELLED = "cancelled", _("Cancelled")
    VOIDED = "voided", pgettext_lazy("kitchen", "Voided")


class Ticket(Audited):
    """A kitchen ticket: one round of a check of Sales, or one made by hand."""

    Status = TicketStatus

    number = models.CharField(_("number"), max_length=16, unique=True)
    day = models.DateField(_("day"))
    sequence = models.PositiveIntegerField(_("number of the day"))
    #: The check of Sales it was fired from (opaque); empty for a ticket made by hand.
    order_id = models.UUIDField(_("check"), null=True, blank=True)
    round_no = models.PositiveIntegerField(_("round"), default=1)
    label = models.CharField(_("label"), max_length=120, blank=True)
    order_type = models.CharField(
        _("type"), max_length=10, choices=OrderType.choices, default=OrderType.DINE_IN
    )
    priority = models.CharField(
        _("priority"), max_length=8, choices=Priority.choices, default=Priority.NORMAL
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    notes = models.TextField(_("notes"), blank=True)
    waiter = models.CharField(_("waiter"), max_length=ACTOR_MAX_LENGTH, blank=True)
    #: When the round was fired (the clock of the card counts from here).
    received_at = models.DateTimeField(_("received at"))
    started_at = models.DateTimeField(pgettext_lazy("kitchen", "started at"), null=True, blank=True)
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    served_at = models.DateTimeField(_("served at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    #: When its sheet was first queued in Printing: only then a void slip or a copy is printed.
    printed_at = models.DateTimeField(_("sent to paper at"), null=True, blank=True)
    rush_count = models.PositiveIntegerField(_("times rushed"), default=0)
    reprint_count = models.PositiveIntegerField(_("times reprinted"), default=0)
    #: Informative, in cents: the kitchen never charges.
    total = models.BigIntegerField(_("total"), default=0)
    is_deleted = models.BooleanField(pgettext_lazy("kitchen", "deleted"), default=False)
    deleted_at = models.DateTimeField(pgettext_lazy("kitchen", "deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("ticket")
        verbose_name_plural = _("tickets")
        ordering = ["-received_at", "-id"]
        indexes = [
            models.Index(
                fields=["status", "received_at"], name="kitchen_ticket_status_idx"
            ),
            models.Index(fields=["order_id"], name="kitchen_ticket_order_idx"),
            models.Index(
                fields=["-received_at", "-id"], name="kitchen_ticket_recent_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=_in("status", TicketStatus), name="kitchen_ticket_status"
            ),
            models.CheckConstraint(
                condition=_in("priority", Priority), name="kitchen_ticket_priority"
            ),
            models.CheckConstraint(
                condition=_in("order_type", OrderType), name="kitchen_ticket_type"
            ),
            models.CheckConstraint(
                condition=Q(round_no__gte=1), name="kitchen_ticket_round"
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def short_number(self) -> str:
        return self.number[-4:]


class TicketItem(UUIDModel):
    """A dish of a ticket: one line of Sales (or one made by hand), with its station frozen."""

    Status = ItemStatus

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="items", verbose_name=_("ticket")
    )
    #: The line of Sales (opaque); empty for a dish made by hand. A menu's line is one dish per dish chosen.
    sale_line_id = models.UUIDField(_("line of the check"), null=True, blank=True)
    #: Which dish of its menu's line it is (1, 2…); 0 = a line ordered on its own (KITCHEN-F06).
    menu_dish = models.PositiveSmallIntegerField(_("dish of the menu"), default=0, db_default=0)
    #: The header of its menu (its kitchen name, else its name); empty out of a menu (KITCHEN-F06).
    menu_name = models.CharField(_("menu"), max_length=200, blank=True, db_default="")
    position = models.PositiveIntegerField(_("position"))
    product_id = models.UUIDField(_("product"), null=True, blank=True)
    category_id = models.UUIDField(_("category"), null=True, blank=True)
    name = models.CharField(_("name"), max_length=200)
    quantity = models.DecimalField(_("quantity"), **QUANTITY)
    unit = models.CharField(_("unit"), max_length=8, default="ud")
    notes = models.CharField(_("note"), max_length=255, blank=True)
    #: The options chosen in the till, by their kitchen names, in the order chosen (KITCHEN-F07).
    modifiers = models.JSONField(_("options"), default=list, blank=True, db_default=[])
    #: The customer's allergy marked on its line in the till, and those of it the dish contains (KITCHEN-F32).
    allergy = models.JSONField(_("customer's allergy"), default=list, blank=True, db_default=[])
    allergy_in_dish = models.JSONField(_("allergy in the dish"), default=list, blank=True, db_default=[])
    station = models.ForeignKey(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
        verbose_name=_("station"),
    )
    station_name = models.CharField(_("station name"), max_length=80, blank=True)
    destination = _destination()
    printer_usage = _printer_usage()
    printer_name = models.CharField(_("printer"), max_length=100, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    void_reason = models.CharField(_("void reason"), max_length=255, blank=True)
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    #: Informative, in cents.
    total = models.BigIntegerField(_("total"), default=0)

    class Meta:
        verbose_name = _("dish")
        verbose_name_plural = _("dishes")
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["station", "status"], name="kitchen_item_station_idx")
        ]
        constraints = [
            # A round saved twice never doubles a dish: one per line, or one per dish of a menu's line.
            models.UniqueConstraint(
                fields=["sale_line_id", "menu_dish"], name="kitchen_item_one_per_line"
            ),
            models.CheckConstraint(
                condition=_in("status", ItemStatus), name="kitchen_item_status"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="kitchen_item_quantity"
            ),
            models.CheckConstraint(
                condition=_in("destination", Destination),
                name="kitchen_item_destination",
            ),
            models.CheckConstraint(
                condition=_in("printer_usage", PrinterUsage), name="kitchen_item_usage"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity:g}× {self.name}"

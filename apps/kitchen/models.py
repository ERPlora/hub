"""Models of the kitchen app: the stations and the routing of products and categories to them, the
kitchen settings, the number of the day, the tickets (a round of a check of Sales, or one made by hand)
with their dishes, and the kitchen's history.

A ticket of a round points at its check of Sales by ``order_id`` and each dish at its line by
``sale_line_id``: opaque references, no foreign key between apps (like Tables). The id of a round's
ticket is the id of its first line, and the id of each dish the id of its line (UUIDv7 that Sales made):
a round the kitchen has not saved yet (no relay in phase 1, queries.py) and the saved one share their
ids. What was sent stays as it was sent: the station, its destination and its printer are frozen on
each dish. Stations and tickets are deleted logically. Phase 1 has no tenancy: every scope shares these
tables; phase 2 moves them to each hub's database.
"""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
MIN_MINUTES = 1
MAX_MINUTES = 120
MAX_VOLUME = 100
#: A station's colour: ``#RRGGBB``.
COLOR_RE = r"^#[0-9A-Fa-f]{6}$"
QUANTITY = {"max_digits": 12, "decimal_places": 3}


class Destination(models.TextChoices):
    BOTH = "both", _("Screen and paper")
    DISPLAY = "display", _("Screen only")
    PRINTER = "printer", _("Paper only")


class PrinterUsage(models.TextChoices):
    KITCHEN = "kitchen", _("Kitchen")
    BAR = "bar", _("Bar")


class OrderType(models.TextChoices):
    DINE_IN = "dine_in", _("Dine in")
    TAKEAWAY = "takeaway", _("Takeaway")
    DELIVERY = "delivery", _("Delivery")


class Priority(models.TextChoices):
    NORMAL = "normal", _("Normal")
    RUSH = "rush", _("Rush")
    VIP = "vip", _("VIP")


class SoundTone(models.TextChoices):
    CHIME = "chime", _("Chime")
    BELL = "bell", _("Bell")
    BUZZER = "buzzer", _("Buzzer")


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
    VOIDED = "voided", _("Voided")


class LogAction(models.TextChoices):
    RECEIVED = "received", _("Received")
    CREATED = "created", _("Created")
    STARTED = "started", _("Fired")
    READY = "ready", _("Ready")
    ITEM_READY = "item_ready", _("Dish ready")
    ITEM_RECALLED = "item_recalled", _("Dish recalled")
    ITEM_VOIDED = "item_voided", _("Dish voided")
    SERVED = "served", _("Served")
    RECALLED = "recalled", _("Recalled")
    CANCELLED = "cancelled", _("Cancelled")
    RUSHED = "rushed", _("Rush")
    UNRUSHED = "unrushed", _("Rush removed")
    REPRINTED = "reprinted", _("Reprinted")
    DELETED = "deleted", _("Deleted")


def _in(field: str, choices) -> Q:
    return Q(**{f"{field}__in": choices.values})


class Audited(UUIDModel):
    """Who created and last changed a row, and when."""

    created_at = models.DateTimeField(
        _("created at"), default=timezone.now, editable=False
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        abstract = True


class Station(Audited):
    """A place where dishes are made (grill, bar, desserts): its screen filter and its printer."""

    name = models.CharField(_("name"), max_length=80)
    color = models.CharField(_("colour"), max_length=7, default="#F97316")
    destination = models.CharField(
        _("destination"),
        max_length=8,
        choices=Destination.choices,
        default=Destination.BOTH,
    )
    printer_usage = models.CharField(
        _("printer function"),
        max_length=8,
        choices=PrinterUsage.choices,
        default=PrinterUsage.KITCHEN,
    )
    #: A given printer of Printing, by its name; empty = the printer of the function.
    printer_name = models.CharField(_("printer"), max_length=100, blank=True)
    sort_order = models.PositiveIntegerField(_("position"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    is_deleted = models.BooleanField(_("deleted"), default=False)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("station")
        verbose_name_plural = _("stations")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(is_deleted=False),
                name="kitchen_station_live_name",
            ),
            models.CheckConstraint(
                condition=_in("destination", Destination),
                name="kitchen_station_destination",
            ),
            models.CheckConstraint(
                condition=_in("printer_usage", PrinterUsage),
                name="kitchen_station_usage",
            ),
            models.CheckConstraint(
                condition=Q(color__regex=COLOR_RE), name="kitchen_station_color"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ProductRoute(Audited):
    """A product of Inventory goes to this station."""

    product = models.OneToOneField(
        "inventory.Product",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("product"),
    )
    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="product_routes",
        verbose_name=_("station"),
    )

    class Meta:
        verbose_name = _("product route")
        verbose_name_plural = _("product routes")

    def __str__(self) -> str:
        return f"{self.product_id} → {self.station_id}"


class CategoryRoute(Audited):
    """A category of Inventory goes to this station (when its product has no route of its own)."""

    category = models.OneToOneField(
        "inventory.Category",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("category"),
    )
    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="category_routes",
        verbose_name=_("station"),
    )

    class Meta:
        verbose_name = _("category route")
        verbose_name_plural = _("category routes")

    def __str__(self) -> str:
        return f"{self.category_id} → {self.station_id}"


class KitchenSettings(UUIDModel):
    """The kitchen display settings: one row, made with the app's tables (migration 0002)."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    show_timer = models.BooleanField(_("show timer"), default=True)
    warning_minutes = models.PositiveSmallIntegerField(
        _("amber warning (minutes)"), default=15
    )
    critical_minutes = models.PositiveSmallIntegerField(
        _("red alert (minutes)"), default=30
    )
    color_coding = models.BooleanField(_("colour semaphore"), default=True)
    sound_enabled = models.BooleanField(_("sound on a new ticket"), default=True)
    sound_volume = models.PositiveSmallIntegerField(_("sound volume"), default=70)
    sound_tone = models.CharField(
        _("sound tone"),
        max_length=8,
        choices=SoundTone.choices,
        default=SoundTone.CHIME,
    )
    print_pass = models.BooleanField(
        _("print the pass when marked ready"), default=False
    )
    works_from_screen = models.BooleanField(
        _("the kitchen works from the screen"), default=True
    )
    #: When «works from the screen» last changed: charging only serves by paper what closed after it.
    screen_changed_at = models.DateTimeField(
        _("screen mode changed at"), null=True, blank=True
    )
    default_order_type = models.CharField(
        _("default order type"),
        max_length=10,
        choices=OrderType.choices,
        default=OrderType.DINE_IN,
    )
    #: The kitchen receives the rounds fired from this moment on (when its tables were made).
    receiving_since = models.DateTimeField(_("receiving since"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("kitchen settings")
        verbose_name_plural = _("kitchen settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="kitchen_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="kitchen_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(
                    warning_minutes__gte=MIN_MINUTES, warning_minutes__lte=MAX_MINUTES
                ),
                name="kitchen_settings_warning_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    critical_minutes__gte=MIN_MINUTES, critical_minutes__lte=MAX_MINUTES
                ),
                name="kitchen_settings_critical_range",
            ),
            models.CheckConstraint(
                condition=Q(warning_minutes__lt=models.F("critical_minutes")),
                name="kitchen_settings_amber_first",
            ),
            models.CheckConstraint(
                condition=Q(sound_volume__lte=MAX_VOLUME),
                name="kitchen_settings_volume",
            ),
            models.CheckConstraint(
                condition=_in("sound_tone", SoundTone), name="kitchen_settings_tone"
            ),
            models.CheckConstraint(
                condition=_in("default_order_type", OrderType),
                name="kitchen_settings_type",
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class DayCounter(UUIDModel):
    """The last ticket number of a business day (``YYYYMMDD-NNNN``), taken with ``select_for_update``."""

    day = models.DateField(_("day"), unique=True)
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("day counter")
        verbose_name_plural = _("day counters")

    def __str__(self) -> str:
        return f"{self.day}: {self.last_number}"


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
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    served_at = models.DateTimeField(_("served at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    #: When its sheet was first queued in Printing: only then a void slip or a copy is printed.
    printed_at = models.DateTimeField(_("sent to paper at"), null=True, blank=True)
    rush_count = models.PositiveIntegerField(_("times rushed"), default=0)
    reprint_count = models.PositiveIntegerField(_("times reprinted"), default=0)
    #: Informative, in cents: the kitchen never charges.
    total = models.BigIntegerField(_("total"), default=0)
    is_deleted = models.BooleanField(_("deleted"), default=False)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

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
    #: The line of Sales (opaque); empty for a dish made by hand.
    sale_line_id = models.UUIDField(
        _("line of the check"), null=True, blank=True, unique=True
    )
    position = models.PositiveIntegerField(_("position"))
    product_id = models.UUIDField(_("product"), null=True, blank=True)
    category_id = models.UUIDField(_("category"), null=True, blank=True)
    name = models.CharField(_("name"), max_length=200)
    quantity = models.DecimalField(_("quantity"), **QUANTITY)
    unit = models.CharField(_("unit"), max_length=8, default="ud")
    notes = models.CharField(_("note"), max_length=255, blank=True)
    station = models.ForeignKey(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
        verbose_name=_("station"),
    )
    station_name = models.CharField(_("station name"), max_length=80, blank=True)
    destination = models.CharField(
        _("destination"),
        max_length=8,
        choices=Destination.choices,
        default=Destination.BOTH,
    )
    printer_usage = models.CharField(
        _("printer function"),
        max_length=8,
        choices=PrinterUsage.choices,
        default=PrinterUsage.KITCHEN,
    )
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


class LogEntry(UUIDModel):
    """One thing that happened in the kitchen (the History)."""

    Action = LogAction

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="log", verbose_name=_("ticket")
    )
    item = models.ForeignKey(
        TicketItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("dish"),
    )
    station = models.ForeignKey(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("station"),
    )
    action = models.CharField(_("action"), max_length=16, choices=Action.choices)
    actor = models.CharField(_("who"), max_length=ACTOR_MAX_LENGTH, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("when"), default=timezone.now)

    class Meta:
        verbose_name = _("history entry")
        verbose_name_plural = _("history")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="kitchen_log_recent_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=_in("action", LogAction), name="kitchen_log_action"
            )
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.ticket.number}"

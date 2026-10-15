"""Models of the table app: the room's zones, its tables, the checks seated at them (with the trail of
tables each one went through), the holds of the reservations and the room settings.

A table's status is NOT stored: it is computed when read (queries.py) from its live checks, its
``blocked`` flag and its live holds, so nothing has to «free a table when no other check is left».
The check of a table points at its open check of Sales by ``order_id``: an opaque reference, no
foreign key between apps. Zones, tables and checks are deleted logically: the history keeps pointing
at them. Phase 1 has no tenancy: every scope shares these tables; phase 2 moves them to each hub's
database.
"""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Trim
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
#: The side of a table box in plan pixels, and the smallest box a person can grab.
BOX = 72
MIN_BOX = 24
MAX_PLAN = 10_000
MAX_CAPACITY = 100
MIN_MINUTES = 1
MAX_MINUTES = 600


class Audited(UUIDModel):
    """Who created and last changed a row, and when (the people of the hub, as a person reads them)."""

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


class TableSettings(UUIDModel):
    """The room settings: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    prompt_guests_on_seat = models.BooleanField(
        _("ask the guests when seating a table"), default=True
    )
    timer_warning_minutes = models.PositiveSmallIntegerField(
        _("amber warning (minutes)"), default=60
    )
    timer_critical_minutes = models.PositiveSmallIntegerField(
        _("red warning (minutes)"), default=90
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("room settings")
        verbose_name_plural = _("room settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="table_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="table_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(
                    timer_warning_minutes__gte=MIN_MINUTES,
                    timer_warning_minutes__lte=MAX_MINUTES,
                ),
                name="table_settings_warning_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    timer_critical_minutes__gte=MIN_MINUTES,
                    timer_critical_minutes__lte=MAX_MINUTES,
                ),
                name="table_settings_critical_range",
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class Zone(Audited):
    """An area of the room (dining room, terrace, bar): a tab of the floor plan."""

    class Color(models.TextChoices):
        PRIMARY = "primary", _("Blue")
        SECONDARY = "secondary", _("Cyan")
        TERTIARY = "tertiary", _("Purple")
        SUCCESS = "success", _("Green")
        WARNING = "warning", _("Amber")
        DANGER = "danger", _("Red")
        MEDIUM = "medium", _("Grey")

    name = models.CharField(_("name"), max_length=100)
    description = models.CharField(_("description"), max_length=500, blank=True)
    color = models.CharField(
        _("color"), max_length=16, choices=Color, default=Color.PRIMARY
    )
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(pgettext_lazy("table", "active"), default=True)
    is_deleted = models.BooleanField(pgettext_lazy("table", "deleted"), default=False)
    deleted_at = models.DateTimeField(pgettext_lazy("table", "deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("zone")
        verbose_name_plural = _("zones")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("name")),
                condition=Q(is_deleted=False),
                name="table_zone_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Table(Audited):
    """A table of the room, with its seats, its shape and its box on the plan of its zone."""

    class Shape(models.TextChoices):
        SQUARE = "square", _("Square")
        ROUND = "round", _("Round")
        RECTANGLE = "rectangle", _("Rectangular")

    zone = models.ForeignKey(
        Zone,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tables",
        verbose_name=_("zone"),
    )
    number = models.CharField(_("number"), max_length=20)
    name = models.CharField(_("name"), max_length=100, blank=True)
    capacity = models.PositiveSmallIntegerField(_("seats"), default=4)
    shape = models.CharField(
        _("shape"), max_length=16, choices=Shape, default=Shape.SQUARE
    )
    position_x = models.PositiveIntegerField(_("x on the plan"), default=0)
    position_y = models.PositiveIntegerField(_("y on the plan"), default=0)
    width = models.PositiveIntegerField(_("width"), default=BOX)
    height = models.PositiveIntegerField(_("height"), default=BOX)
    # Out of service (TABLE-F05): the only status a person sets; the others are computed.
    blocked = models.BooleanField(_("blocked"), default=False)
    is_active = models.BooleanField(pgettext_lazy("table", "active"), default=True)
    is_deleted = models.BooleanField(pgettext_lazy("table", "deleted"), default=False)
    deleted_at = models.DateTimeField(pgettext_lazy("table", "deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("table")
        verbose_name_plural = _("tables")
        ordering = ["number", "id"]
        constraints = [
            # «m1» and «M1 » are the same table on the floor; two tables without a zone too.
            models.UniqueConstraint(
                Lower(Trim("number")),
                "zone",
                condition=Q(is_deleted=False),
                nulls_distinct=False,
                name="table_table_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=1, capacity__lte=MAX_CAPACITY),
                name="table_table_capacity",
            ),
            models.CheckConstraint(
                condition=Q(width__gte=MIN_BOX, height__gte=MIN_BOX),
                name="table_table_box",
            ),
        ]

    def __str__(self) -> str:
        return self.number


class TableSession(Audited):
    """A check seated at a table (the old «session»): who sits, since when, who serves them and which
    open check of Sales holds what they ordered."""

    class Status(models.TextChoices):
        OPEN = "open", pgettext_lazy("table check", "Open")
        CLOSED = "closed", _("Closed")
        TRANSFERRED = "transferred", _("Transferred")
        MERGED = "merged", _("Merged")
        PARKED = "parked", _("Parked")

    table = models.ForeignKey(
        Table,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name=_("table"),
    )
    # The open check of Sales (sale.Order): an opaque reference, no foreign key between apps.
    order_id = models.UUIDField(
        _("check of Sales"), null=True, blank=True, db_index=True
    )
    guests_count = models.PositiveSmallIntegerField(_("guests"), default=1)
    waiter_id = models.CharField(_("waiter id"), max_length=64, blank=True)
    waiter_name = models.CharField(_("waiter"), max_length=ACTOR_MAX_LENGTH, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status, default=Status.OPEN
    )
    opened_at = models.DateTimeField(pgettext_lazy("table check", "opened at"), default=timezone.now)
    closed_at = models.DateTimeField(pgettext_lazy("table check", "closed at"), null=True, blank=True)
    notes = models.TextField(_("notes"), max_length=2000, blank=True)
    transferred_from = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("transferred from"),
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=pgettext_lazy("table check", "merged into"),
    )
    split_from = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=pgettext_lazy("table check", "split from"),
    )
    is_deleted = models.BooleanField(pgettext_lazy("table", "deleted"), default=False)
    deleted_at = models.DateTimeField(pgettext_lazy("table", "deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("table check")
        verbose_name_plural = _("table checks")
        ordering = ["-opened_at", "-id"]
        indexes = [
            models.Index(fields=["table", "status"], name="table_session_table_status")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(guests_count__gte=1), name="table_session_guests"
            ),
            # A parked check sits at no table and an open one at its table; a finished one keeps the
            # table it was at, or none when it ended parked (Sales charged or voided it meanwhile).
            models.CheckConstraint(
                condition=Q(status="parked", table__isnull=True)
                | Q(status="open", table__isnull=False)
                | Q(status__in=["closed", "transferred", "merged"]),
                name="table_session_table_by_status",
            ),
            # One check of Sales is in one live table check at most.
            models.UniqueConstraint(
                fields=["order_id"],
                condition=Q(
                    status__in=["open", "parked"],
                    is_deleted=False,
                    order_id__isnull=False,
                ),
                name="table_session_order_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.table or '—'} · {self.get_status_display()}"


class SessionMove(UUIDModel):
    """A stretch of a check at a table (the trail of a check through the room): why it started there and
    why it left. Kept when the check is deleted; no screen shows it (the admin does)."""

    class Reason(models.TextChoices):
        OPENED = "opened", _("Seated")
        TRANSFERRED = "transferred", _("Transferred")
        RESTORED = "restored", _("Seated again")
        SPLIT = "split", _("Split")

    class Release(models.TextChoices):
        NONE = "", _("Still there")
        PARKED = "parked", _("Parked")
        TRANSFERRED = "transferred", _("Transferred")
        MERGED = "merged", _("Merged")
        CLOSED = "closed", _("Closed")

    session = models.ForeignKey(
        TableSession,
        on_delete=models.PROTECT,
        related_name="moves",
        verbose_name=_("table check"),
    )
    table = models.ForeignKey(
        Table, on_delete=models.PROTECT, related_name="+", verbose_name=_("table")
    )
    assigned_at = models.DateTimeField(_("from"))
    released_at = models.DateTimeField(_("until"), null=True, blank=True)
    assignment_reason = models.CharField(
        _("why it started"), max_length=16, choices=Reason
    )
    release_reason = models.CharField(
        _("why it ended"), max_length=16, choices=Release, blank=True
    )

    class Meta:
        verbose_name = _("check's stretch at a table")
        verbose_name_plural = _("checks' stretches at tables")
        ordering = ["assigned_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session"],
                condition=Q(released_at__isnull=True),
                name="table_move_one_live",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.table} · {self.get_assignment_reason_display()}"


class Hold(Audited):
    """A table set aside for a reservation (or by hand): nobody sits yet, it is no check. It paints the
    table Reserved from an hour before ``held_from`` until ``held_until``."""

    class Source(models.TextChoices):
        RESERVATION = "reservation", _("Reservation")
        MANUAL = "manual", _("By hand")

    class Status(models.TextChoices):
        HELD = "held", pgettext_lazy("table hold", "Held")
        CONSUMED = "consumed", _("Seated")
        RELEASED = "released", pgettext_lazy("table hold", "Released")
        EXPIRED = "expired", _("Expired")

    table = models.ForeignKey(
        Table, on_delete=models.PROTECT, related_name="holds", verbose_name=_("table")
    )
    source = models.CharField(_("source"), max_length=16, choices=Source)
    # Who asked for it and on which row of theirs: an opaque reference.
    source_ref = models.CharField(_("reference"), max_length=100)
    held_from = models.DateTimeField(_("from"))
    held_until = models.DateTimeField(_("until"))
    party_size = models.PositiveSmallIntegerField(_("guests"), default=0)
    # What the plan paints on the table: the reservation's name, kept only while the hold lives.
    label = models.CharField(_("name"), max_length=200, blank=True)
    # Whose reservation it is (Customers' card): to forget the name when the card is erased (F31).
    customer_id = models.UUIDField(_("customer"), null=True, blank=True, db_index=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status, default=Status.HELD
    )

    class Meta:
        verbose_name = _("hold")
        verbose_name_plural = _("holds")
        ordering = ["held_from", "id"]
        indexes = [
            models.Index(
                fields=["table", "status", "held_until"], name="table_hold_live"
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_ref"], name="table_hold_source_unique"
            ),
            models.CheckConstraint(
                condition=Q(held_until__gt=models.F("held_from")),
                name="table_hold_window",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.table} · {self.label or self.source_ref}"

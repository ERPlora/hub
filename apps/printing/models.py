"""Models of the printing app.

- ``Printer`` is a printer of the business: its name, how it is connected (network, USB, Bluetooth or the
  computer's own printer), its address, its paper and the function it prints (receipts, kitchen, bar,
  labels). Never deleted: the queue names it; it is deactivated instead.
- ``Settings`` (one row at most; without it the factory values apply) says whether the receipt prints and
  the drawer opens at checkout, how many copies, and which printer prints each function.
- ``PrintJob`` is a job of the print queue: the structured document the app's renderer paints (or the A4
  page for the computer's printer), its function, its printer, its state and who retried or cancelled it.
  Nobody deletes a job: the platform's hourly prune forgets the ones that ended over 30 days ago.
- ``PrintDevice`` is a device that prints (the old hub's print host, hub#342): the one with the ERPlora app
  next to the printers, set up by whoever sets up the printers, with the printers it reaches. Only it takes,
  confirms and fails their jobs. Never deleted (the queue names it): it is retired.
"""

import hashlib

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.printing.documents import DOCUMENT_TYPES

ACTOR_MAX_LENGTH = 128
ERROR_MAX_LENGTH = 500


class Usage(models.TextChoices):
    """What a printer prints: the role (the old hub's station) every document goes to."""

    RECEIPT = "receipt", _("Receipt")
    KITCHEN = "kitchen", _("Kitchen")
    BAR = "bar", _("Bar")
    LABEL = "label", _("Label")


class Printer(UUIDModel):
    """A printer of the business, the way the app on the device next to it reaches it."""

    class Kind(models.TextChoices):
        NETWORK = "network", _("Network")
        USB = "usb", _("USB")
        BLUETOOTH = "bluetooth", _("Bluetooth")
        SYSTEM = "system", _("System printer (A4)")

    class Paper(models.IntegerChoices):
        MM_80 = 80, _("80 mm")
        MM_58 = 58, _("58 mm")

    name = models.CharField(_("name"), max_length=100)
    kind = models.CharField(_("connection"), max_length=16, choices=Kind.choices)
    address = models.CharField(_("address"), max_length=255, blank=True)
    port = models.PositiveIntegerField(_("port"), null=True, blank=True)
    paper_width = models.PositiveSmallIntegerField(_("paper width"), choices=Paper.choices, default=Paper.MM_80)
    usage = models.CharField(_("function"), max_length=16, choices=Usage.choices)
    is_active = models.BooleanField(_("active"), default=True)
    last_printed_at = models.DateTimeField(_("last printed at"), null=True, blank=True)
    last_failed_at = models.DateTimeField(_("last failed at"), null=True, blank=True)
    last_error = models.CharField(_("last error"), max_length=ERROR_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(_("created by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("printer")
        verbose_name_plural = _("printers")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="printing_printer_name_unique"),
            models.CheckConstraint(condition=~Q(name=""), name="printing_printer_name_given"),
            models.CheckConstraint(condition=Q(paper_width__in=[58, 80]), name="printing_printer_paper_width"),
            models.CheckConstraint(
                condition=Q(kind="network", port__isnull=False, port__gte=1, port__lte=65535)
                | (~Q(kind="network") & Q(port__isnull=True)),
                name="printing_printer_port",
            ),
            models.CheckConstraint(
                condition=(Q(kind="system") & Q(address="") & Q(usage="receipt")) | (~Q(kind="system") & ~Q(address="")),
                name="printing_printer_address",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def target(self) -> str:
        """The ``printer_id`` the app's print commands take (``discovery::parse_print_target``)."""
        if self.kind == self.Kind.NETWORK:
            return f"network:{self.address}:{self.port}"
        if self.kind == self.Kind.SYSTEM:
            return "system"
        return f"{self.kind}:{self.address}"

    @property
    def format(self) -> str:
        """The paper it prints: A4 pages on the computer's printer, receipt paper on a thermal one."""
        return PrintJob.Format.A4 if self.kind == self.Kind.SYSTEM else PrintJob.Format.RECEIPT


class Settings(UUIDModel):
    """The printing settings of the business: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    print_receipt_on_sale = models.BooleanField(_("print the receipt at checkout"), default=True)
    open_drawer_on_sale = models.BooleanField(_("open the drawer at checkout"), default=False)
    receipt_copies = models.PositiveSmallIntegerField(_("receipt copies"), default=1)
    receipt_printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("receipt printer")
    )
    kitchen_printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("kitchen printer")
    )
    bar_printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("bar printer")
    )
    label_printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("label printer")
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(_("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("printing settings")
        verbose_name_plural = _("printing settings")
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="printing_settings_single_row"),
            models.CheckConstraint(condition=Q(singleton=True), name="printing_settings_singleton"),
            models.CheckConstraint(
                condition=Q(receipt_copies__gte=1, receipt_copies__lte=3), name="printing_settings_receipt_copies"
            ),
        ]

    def __str__(self) -> str:
        return str(_("printing settings"))


class PrintDevice(UUIDModel):
    """A device that prints the jobs of the printers it reaches. It is known by the digest of its own id (the
    SPA's ``X-Device-Id``, the ``deviceId`` of /ws/print's hello), never by the id itself: that id is what proves
    the device, and a queue or a screen that showed it let anybody print as the till (hub#2551)."""

    name = models.CharField(_("name"), max_length=100)
    #: SHA-256 of the device's id (``key_of``); empty (null) only for one added by hand in the admin, which no
    #: device matches.
    key = models.CharField(_("key"), max_length=64, unique=True, null=True, blank=True)
    printers = models.ManyToManyField(Printer, related_name="devices", blank=True, verbose_name=_("printers"))
    registered_at = models.DateTimeField(_("set up at"), auto_now_add=True)
    registered_by = models.CharField(_("set up by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    last_seen_at = models.DateTimeField(_("last asked for a job at"), null=True, blank=True)
    retired_at = models.DateTimeField(_("retired at"), null=True, blank=True)
    retired_by = models.CharField(_("retired by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("printing device")
        verbose_name_plural = _("printing devices")
        ordering = ["name", "id"]
        constraints = [models.CheckConstraint(condition=~Q(name=""), name="printing_device_name_given")]

    def __str__(self) -> str:
        return self.name

    @staticmethod
    def key_of(device_id: str) -> str:
        """The digest a device is kept by: its id proves the device, the digest proves nothing."""
        return hashlib.sha256(device_id.strip().encode()).hexdigest()


class PrintJob(UUIDModel):
    """A job of the print queue. A retry or a cancel stamps who, when and why; it is forgotten 30 days after
    it ended (``printing.job.prune``)."""

    class Kind(models.TextChoices):
        DOCUMENT = "document", _("Document")
        TEST_PAGE = "test_page", _("Test page")
        DRAWER = "drawer", _("Open the drawer")

    class Format(models.TextChoices):
        RECEIPT = "receipt", _("Receipt paper")
        A4 = "a4", _("A4")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent")
        DONE = "done", _("Printed")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")

    job_key = models.CharField(_("job key"), max_length=128, unique=True)
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices, default=Kind.DOCUMENT)
    document_type = models.CharField(_("document type"), max_length=32, blank=True)
    document = models.JSONField(_("document"), default=dict, blank=True, encoder=DjangoJSONEncoder)
    html = models.TextField(_("A4 page"), blank=True)
    format = models.CharField(_("paper"), max_length=16, choices=Format.choices, default=Format.RECEIPT)
    usage = models.CharField(_("function"), max_length=16, choices=Usage.choices)
    printer = models.ForeignKey(
        Printer, on_delete=models.PROTECT, null=True, blank=True, related_name="jobs", verbose_name=_("printer")
    )
    copies = models.PositiveSmallIntegerField(_("copies"), default=1)
    open_drawer = models.BooleanField(_("open the drawer"), default=False)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    leased_until = models.DateTimeField(_("answer due by"), null=True, blank=True)
    #: The device that took it last: by its registration (what a confirmation is checked against) and by its
    #: name then (what the queue shows), never by the id it sent.
    print_device = models.ForeignKey(
        PrintDevice, on_delete=models.PROTECT, null=True, blank=True, related_name="jobs", verbose_name=_("device")
    )
    device = models.CharField(_("device name"), max_length=ACTOR_MAX_LENGTH, blank=True)
    last_error = models.CharField(_("last error"), max_length=ERROR_MAX_LENGTH, blank=True)
    reference = models.CharField(_("reference"), max_length=64, blank=True)
    source_app = models.CharField(_("asked by app"), max_length=32, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    created_by = models.CharField(_("created by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    printed_at = models.DateTimeField(_("printed at"), null=True, blank=True)
    failed_at = models.DateTimeField(_("failed at"), null=True, blank=True)
    retried_at = models.DateTimeField(_("retried at"), null=True, blank=True)
    retried_by = models.CharField(_("retried by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancelled_by = models.CharField(_("cancelled by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    cancel_reason = models.CharField(_("cancel reason"), max_length=ERROR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("print job")
        verbose_name_plural = _("print jobs")
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "created_at"], name="printing_job_status_created")]
        constraints = [
            models.CheckConstraint(condition=Q(copies__gte=1, copies__lte=5), name="printing_job_copies"),
            models.CheckConstraint(
                condition=~Q(kind="document") | Q(document_type__in=DOCUMENT_TYPES), name="printing_job_document_type"
            ),
            # A printed or cancelled job lets its document go (RGPD): only a live A4 job needs its page.
            models.CheckConstraint(
                condition=~Q(format="a4") | ~Q(html="") | Q(status__in=["done", "cancelled"]),
                name="printing_job_a4_page",
            ),
        ]

    def __str__(self) -> str:
        what = self.document_type or self.kind
        return f"{what} {self.reference}".strip()

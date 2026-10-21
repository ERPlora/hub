"""Django admin of the printing app: full CRUD over its tables, for the platform's staff only.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com and has
full CRUD over every table. What it saves does not go through the operations (no event, no wake for the
devices); the database still refuses two printers with one name, a port out of range, an address the
connection cannot have, more than five copies and an A4 job without its page. A device that prints is set
up from the device itself (its key is the digest of the device's own id): the admin never types or shows a key.
"""

from django.contrib import admin

from apps.printing.models import PrintDevice, Printer, PrintJob, Settings

READ_ONLY = (
    "id",
    "created_at",
    "updated_at",
    "last_printed_at",
    "last_failed_at",
    "sent_at",
    "printed_at",
    "failed_at",
    "retried_at",
    "cancelled_at",
    "registered_at",
    "last_seen_at",
    "retired_at",
)


def _readonly(model) -> tuple:
    names = {field.name for field in model._meta.get_fields()}
    return tuple(name for name in READ_ONLY if name in names)


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "print_receipt_on_sale", "open_drawer_on_sale", "receipt_copies", "updated_at")
    readonly_fields = _readonly(Settings)


@admin.register(Printer)
class PrinterAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "address", "port", "paper_width", "usage", "is_active", "last_printed_at")
    list_filter = ("kind", "usage", "is_active")
    search_fields = ("name", "address")
    readonly_fields = _readonly(Printer)


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "document_type", "reference", "usage", "printer", "status", "attempts")
    list_filter = ("status", "usage", "kind", "format")
    search_fields = ("reference", "job_key", "source_app")
    list_select_related = ("printer",)
    readonly_fields = _readonly(PrintJob)


@admin.register(PrintDevice)
class PrintDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "registered_at", "registered_by", "last_seen_at", "retired_at")
    list_filter = ("retired_at",)
    search_fields = ("name", "registered_by")
    filter_horizontal = ("printers",)
    readonly_fields = ("key", *_readonly(PrintDevice))

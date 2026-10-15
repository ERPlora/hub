"""Django admin of the online booking app: full CRUD on both tables for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations' rules (a
booking's appointment, the page's limits), so it warns rather than prevents, and it leaves no event. What the
database fills in (ids and timestamps) is shown, not edited. A link's hash can be emptied (the link is revoked);
it never gives the link back.
"""

from django.contrib import admin

from apps.online_booking.models import Booking, Settings


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = (
        "is_enabled",
        "page_title",
        "primary_color",
        "require_email",
        "updated_at",
    )
    readonly_fields = ("id", "updated_at")
    fields = (
        "id",
        "is_enabled",
        "page_title",
        "welcome_message",
        "primary_color",
        "logo_url",
        "require_email",
        "max_upcoming_per_customer",
        "allow_staff_selection",
        "allow_notes",
        "confirmation_message",
        "cancellation_policy",
        "updated_by",
        "updated_at",
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("appointment", "created_at", "token_hash")
    list_select_related = ("appointment",)
    search_fields = ("appointment__number", "appointment__customer_name")
    date_hierarchy = "created_at"
    raw_id_fields = ("appointment",)
    readonly_fields = ("id", "created_at")
    fields = ("id", "appointment", "token_hash", "requester", "created_at")

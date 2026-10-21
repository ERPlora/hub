"""Django admin of the WhatsApp inbox: CRUD for the platform's staff (round 12, PLAN §17).

Messages are read only, received and sent alike (WORKBOOK «Modelo»): they are what WhatsApp carried;
a conversation's data is corrected by erasing it, never by editing a message. The channel, and the
templates Meta holds, are erplora.com's copy: what is changed here is overwritten by its next push; a
template's hand-over to Meta (its key, state and reason) is shown, never edited.
"""

from django.contrib import admin

from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = (
        "sent_at",
        "direction",
        "origin",
        "kind",
        "body",
        "status",
        "wa_message_id",
    )
    readonly_fields = fields
    ordering = ("sent_at",)
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ("created_at", "author_name", "text")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "phone",
        "contact_name",
        "customer",
        "assigned_to",
        "status",
        "unread_count",
        "last_message_at",
    )
    list_filter = ("status",)
    search_fields = ("phone", "contact_name", "customer__name")
    raw_id_fields = ("customer", "assigned_to")
    readonly_fields = ("created_at", "updated_at")
    inlines = [MessageInline, NoteInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sent_at", "conversation", "direction", "origin", "kind", "status")
    list_filter = ("direction", "origin", "source", "status", "kind")
    search_fields = ("wa_message_id", "conversation__phone", "body")
    raw_id_fields = ("conversation", "sent_by")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("created_at", "conversation", "author_name", "text")
    search_fields = ("text", "author_name", "conversation__phone")
    raw_id_fields = ("conversation", "author")


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "language", "category", "status", "submit_state", "delete_state", "variables", "synced_at")
    list_filter = ("status", "category", "language", "submit_state", "delete_state")
    search_fields = ("name", "body")
    readonly_fields = (
        "supported",
        "submit_state",
        "submit_key",
        "submit_error_code",
        "submit_error",
        "submit_at",
        "deleted_at",
        "delete_state",
    )


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = (
        "host",
        "phone_number",
        "display_name",
        "status",
        "monthly_usage",
        "monthly_limit",
        "usage_month",
        "version",
    )
    search_fields = ("host", "phone_number", "display_name")
    readonly_fields = ("host", "updated_at")

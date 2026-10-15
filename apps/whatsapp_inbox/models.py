"""Models of the WhatsApp inbox: the channel's state, conversations, their messages and notes, and the
copy of the templates Meta approved (WORKBOOK «Para quien lo mantiene → Modelo»).

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live notifications
are per scope. Phase 2 moves them to each hub's database. A conversation is live while ``erased_at``
is empty; erased (WHATSAPP_INBOX-F10, F11) it keeps no personal data and frees its number.
"""

import datetime as dt

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.customer.search import normalize

#: Meta's customer service window: free text only this long after the customer's last message.
WINDOW = dt.timedelta(hours=24)


def name_key(text: str) -> str:
    """A name as people say it (by voice too): lowercased, without accents, emoji or punctuation,
    single spaces («  Ána  López 🌸 » → «ana lopez»)."""
    plain = normalize(text)
    kept = "".join(char if char.isalnum() or char.isspace() else " " for char in plain)
    return " ".join(kept.split())


class Channel(UUIDModel):
    """The business's WhatsApp number as erplora.com reports it: one row, written only by the SaaS."""

    class Status(models.TextChoices):
        NOT_CONNECTED = "not_connected", pgettext_lazy("whatsapp channel", "Not connected")
        CONNECTED = "connected", pgettext_lazy("whatsapp channel", "Connected")
        RECONNECT_NEEDED = "reconnect_needed", pgettext_lazy("whatsapp channel", "Needs reconnecting")

    slot = models.PositiveSmallIntegerField(_("slot"), default=1, editable=False)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.NOT_CONNECTED
    )
    # The business's own number (E.164) and the name WhatsApp shows for it.
    phone_number = models.CharField(_("phone number"), max_length=16, blank=True)
    display_name = models.CharField(_("display name"), max_length=200, blank=True)
    # The plan's monthly allowance of messages sent (0 = no cap) and what is spent, with the month
    # (``YYYY-MM``) the figure counts: another month's figure counts as nothing spent.
    monthly_limit = models.PositiveIntegerField(_("monthly limit"), default=0)
    monthly_usage = models.PositiveIntegerField(_("used this month"), default=0)
    usage_month = models.CharField(_("month of the figure"), max_length=7, blank=True)
    # The SaaS's version of this state: an older push is ignored.
    version = models.BigIntegerField(_("version"), default=0)
    synced_at = models.DateTimeField(_("synced at"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("WhatsApp channel")
        verbose_name_plural = _("WhatsApp channel")
        constraints = [
            models.UniqueConstraint(
                fields=["slot"], name="whatsapp_inbox_channel_singleton"
            ),
            models.CheckConstraint(
                condition=Q(slot=1), name="whatsapp_inbox_channel_slot"
            ),
        ]

    def __str__(self) -> str:
        return self.phone_number or str(self.get_status_display())

    def cap_reached(self, month: str) -> bool:
        """Whether the plan's messages of ``month`` (``YYYY-MM``) are spent; never without a cap."""
        return (
            self.monthly_limit > 0
            and self.usage_month == month
            and self.monthly_usage >= self.monthly_limit
        )


class Conversation(UUIDModel):
    """One customer's WhatsApp number and everything said with it."""

    class Status(models.TextChoices):
        OPEN = "open", pgettext_lazy("whatsapp conversation", "Open")
        PENDING = "pending", pgettext_lazy("whatsapp conversation", "Pending")
        CLOSED = "closed", pgettext_lazy("whatsapp conversation", "Closed")

    class EraseStatus(models.TextChoices):
        # What erplora.com still holds of an erased conversation (WHATSAPP_INBOX-F10, F11).
        NONE = "", _("Not erased")
        PENDING = "pending", _("erplora.com has not confirmed the erasure yet")
        DONE = "done", _("erplora.com confirmed the erasure")

    # E.164 (``+34600111222``); empty once erased.
    phone = models.CharField(_("phone"), max_length=16, blank=True)
    # The name the customer has in WhatsApp (their profile), as Meta sends it.
    contact_name = models.CharField(_("WhatsApp name"), max_length=200, blank=True)
    # ``contact_name`` as people say it (``name_key``): what a reference by voice or text is compared to.
    contact_search = models.CharField(_("WhatsApp name, searchable"), max_length=200, blank=True, editable=False)
    customer = models.ForeignKey(
        "customer.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="whatsapp_conversations",
        verbose_name=_("customer"),
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="whatsapp_conversations",
        verbose_name=_("assigned to"),
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.OPEN
    )
    unread_count = models.PositiveIntegerField(_("unread"), default=0)
    last_message_at = models.DateTimeField(_("last message"), null=True, blank=True)
    last_message_preview = models.CharField(
        _("last message text"), max_length=160, blank=True
    )
    last_message_direction = models.CharField(
        _("last message direction"), max_length=10, blank=True
    )
    # The customer's last message: Meta's 24-hour window runs from it.
    last_inbound_at = models.DateTimeField(
        _("customer's last message"), null=True, blank=True
    )
    # Meta's type of the last message: the inbox names it when it has no text (a photo, a location).
    last_message_kind = models.CharField(_("last message type"), max_length=32, blank=True)
    erased_at = models.DateTimeField(_("erased at"), null=True, blank=True)
    erase_status = models.CharField(
        _("erasure at erplora.com"), max_length=10, choices=EraseStatus.choices, default=EraseStatus.NONE, blank=True
    )
    # The number erplora.com has to forget, kept only until it confirms (then emptied).
    erase_phone = models.CharField(_("number to erase at erplora.com"), max_length=16, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("conversation")
        verbose_name_plural = _("conversations")
        ordering = ["-last_message_at", "-id"]
        constraints = [
            # One live conversation per number: erasing frees it (WHATSAPP_INBOX-F10).
            models.UniqueConstraint(
                fields=["phone"],
                condition=Q(erased_at__isnull=True),
                name="whatsapp_inbox_conversation_phone_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "-last_message_at"], name="whatsapp_conv_status_idx"
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.contact_name} ({self.phone})" if self.contact_name else self.phone
        )

    def save(self, *args, **kwargs):
        self.contact_search = name_key(self.contact_name)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "contact_name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "contact_search"}
        super().save(*args, **kwargs)

    def window_open(self, now: dt.datetime) -> bool:
        """Whether free text may be sent at ``now`` (Meta's 24 hours from the customer's last message)."""
        return self.last_inbound_at is not None and now < self.last_inbound_at + WINDOW

    def window_expires_at(self) -> dt.datetime | None:
        return self.last_inbound_at + WINDOW if self.last_inbound_at else None


class Message(UUIDModel):
    """One WhatsApp message of a conversation, as Meta delivered it or as the Hub sent it."""

    class Direction(models.TextChoices):
        INBOUND = "inbound", _("From the customer")
        OUTBOUND = "outbound", _("From the business")

    class Origin(models.TextChoices):
        CUSTOMER = "customer", pgettext_lazy("whatsapp message", "Customer")
        PHONE_APP = "phone_app", _("WhatsApp Business app")
        HUB = "hub", pgettext_lazy("whatsapp message", "Hub")

    class Source(models.TextChoices):
        LIVE = "live", pgettext_lazy("whatsapp message", "Live")
        HISTORY = "history", pgettext_lazy("whatsapp message", "History")

    class Status(models.TextChoices):
        RECEIVED = "received", pgettext_lazy("whatsapp message", "Received")
        # Kept by the Hub, not yet handed to erplora.com / handed over without a final answer.
        QUEUED = "queued", pgettext_lazy("whatsapp message", "Queued")
        SENDING = "sending", pgettext_lazy("whatsapp message", "Sending")
        SENT = "sent", pgettext_lazy("whatsapp message", "Sent")
        DELIVERED = "delivered", pgettext_lazy("whatsapp message", "Delivered")
        READ = "read", pgettext_lazy("whatsapp message", "Read")
        FAILED = "failed", pgettext_lazy("whatsapp message", "Not delivered")

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("conversation"),
    )
    direction = models.CharField(
        _("direction"),
        max_length=10,
        choices=Direction.choices,
        default=Direction.INBOUND,
    )
    origin = models.CharField(
        _("origin"), max_length=10, choices=Origin.choices, default=Origin.CUSTOMER
    )
    source = models.CharField(
        _("source"), max_length=10, choices=Source.choices, default=Source.LIVE
    )
    # Meta's message type as it came (text, image, audio, video, document, sticker, location,
    # contacts, interactive, button, reaction, template, media_placeholder, unsupported…).
    kind = models.CharField(_("type"), max_length=32, default="text")
    body = models.TextField(_("text"), blank=True)
    # An attachment is kept by erplora.com: its URL there, as the browser opens it.
    media_url = models.URLField(_("attachment URL"), max_length=1000, blank=True)
    media_mime_type = models.CharField(_("attachment type"), max_length=120, blank=True)
    media_filename = models.CharField(_("attachment name"), max_length=255, blank=True)
    media_caption = models.TextField(_("attachment caption"), blank=True)
    template_name = models.CharField(_("template"), max_length=512, blank=True)
    template_language = models.CharField(
        _("template language"), max_length=15, blank=True
    )
    # The values of a template's {{1}}…{{n}}, kept to hand it to erplora.com again on a retry.
    template_variables = models.JSONField(_("template variables"), default=list, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.RECEIVED
    )
    error_code = models.CharField(_("error code"), max_length=64, blank=True)
    error_message = models.CharField(_("error"), max_length=500, blank=True)
    # Meta's id; empty (NULL) while a message the Hub queued has not left yet.
    wa_message_id = models.CharField(_("WhatsApp message id"), max_length=255, null=True, blank=True)
    # The key the Hub sends with a message (Idempotency-Key): a retry never sends it twice.
    client_message_id = models.UUIDField(_("send key"), null=True, blank=True)
    reply_to = models.CharField(_("answers"), max_length=255, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("sent by"),
    )
    # Meta's own object, verbatim (what the Hub does not lift into columns).
    payload = models.JSONField(_("Meta's object"), default=dict, blank=True)
    # When it was said (Meta's time); a history message keeps its own.
    sent_at = models.DateTimeField(_("said at"))
    status_at = models.DateTimeField(_("status at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("message")
        verbose_name_plural = _("messages")
        ordering = ["-sent_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["wa_message_id"], name="whatsapp_inbox_message_wa_id_unique"
            ),
            models.UniqueConstraint(
                fields=["client_message_id"],
                condition=Q(client_message_id__isnull=False),
                name="whatsapp_inbox_message_client_id_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["conversation", "-sent_at"], name="whatsapp_msg_conv_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.wa_message_id or str(self.client_message_id or self.pk)


class Note(UUIDModel):
    """An internal note on a conversation: the team sees it, the customer never."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name=_("conversation"),
    )
    text = models.TextField(_("text"))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("author"),
    )
    # The author's name when it was written: the note keeps it if the person leaves.
    author_name = models.CharField(_("author name"), max_length=200, blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("note")
        verbose_name_plural = _("notes")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.text[:60]


class Template(UUIDModel):
    """The local copy of a message template of the business's WhatsApp account (synced by the SaaS)."""

    class Category(models.TextChoices):
        UTILITY = "UTILITY", pgettext_lazy("whatsapp template", "Utility")
        MARKETING = "MARKETING", pgettext_lazy("whatsapp template", "Marketing")
        AUTHENTICATION = "AUTHENTICATION", pgettext_lazy("whatsapp template", "Authentication")

    class Status(models.TextChoices):
        APPROVED = "APPROVED", pgettext_lazy("whatsapp template", "Approved")
        PENDING = "PENDING", pgettext_lazy("whatsapp template", "In review")
        REJECTED = "REJECTED", pgettext_lazy("whatsapp template", "Rejected")
        PAUSED = "PAUSED", pgettext_lazy("whatsapp template", "Paused by Meta")
        DISABLED = "DISABLED", pgettext_lazy("whatsapp template", "Disabled by Meta")
        DELETED = "DELETED", _("Deleted in WhatsApp Manager")

    name = models.CharField(_("name"), max_length=512)
    language = models.CharField(_("language"), max_length=15)
    category = models.CharField(
        _("category"), max_length=16, choices=Category.choices, default=Category.UTILITY
    )
    status = models.CharField(
        _("status in Meta"),
        max_length=10,
        choices=Status.choices,
        default=Status.APPROVED,
    )
    header = models.CharField(_("header"), max_length=200, blank=True)
    body = models.TextField(_("body"), blank=True)
    footer = models.CharField(_("footer"), max_length=200, blank=True)
    # How many variables the body takes ({{1}}…{{n}}).
    variables = models.PositiveSmallIntegerField(_("variables"), default=0)
    rejected_reason = models.CharField(_("Meta's reason"), max_length=500, blank=True)
    meta_id = models.CharField(_("Meta id"), max_length=64, blank=True)
    synced_at = models.DateTimeField(_("synced at"), null=True, blank=True)

    class Meta:
        verbose_name = _("template")
        verbose_name_plural = _("templates")
        ordering = ["name", "language", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "language"],
                name="whatsapp_inbox_template_name_language_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.language})"

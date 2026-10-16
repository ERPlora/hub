"""Models of the customer app: the cards, their segmentation, their timeline, purchases and consent.

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live notifications
are per scope. Phase 2 moves them to each hub's database. Money is in cents.

A card is live while ``deleted_at`` is empty; deleted (CUSTOMER-F07), merged into another
(``merged_into``, F13) or erased (``erased_at``, F16) it is no longer read by anyone.
"""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.customer.search import searchable

#: The fields ``search_text`` is built from, in this order.
SEARCHED_FIELDS = ("name", "email", "phone", "tax_id", "company_name")


class CustomerGroup(UUIDModel):
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    color = models.CharField(_("color"), max_length=20, default="primary")
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    # An inactive group is offered on no card; the cards that have it keep it.
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("group")
        verbose_name_plural = _("groups")
        ordering = ["name", "id"]
        constraints = [
            # One active group per name, whatever its case (customers#94): an inactive one frees it.
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(is_active=True),
                name="customer_group_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class CustomerTag(UUIDModel):
    name = models.CharField(_("name"), max_length=60)
    color = models.CharField(_("color"), max_length=20, default="primary")
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("tag")
        verbose_name_plural = _("tags")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(is_active=True),
                name="customer_tag_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class CustomerQuerySet(models.QuerySet):
    def live(self) -> "CustomerQuerySet":
        """The cards anyone may read: not deleted, merged nor erased (those three set ``deleted_at``)."""
        return self.filter(deleted_at__isnull=True)


class Customer(UUIDModel):
    class Stage(models.TextChoices):
        LEAD = "lead", _("Lead")
        PROSPECT = "prospect", _("Prospect")
        FIRST_PURCHASE = "first_purchase", _("1st purchase")
        ACTIVE = "active", _("Active")
        AT_RISK = "at_risk", _("At risk")
        DORMANT = "dormant", _("Dormant")
        CHURNED = "churned", _("Churned")
        VIP = "vip", _("VIP")

    class Source(models.TextChoices):
        WALK_IN = "walk_in", _("Walk-in")
        WEBSITE = "website", _("Website")
        PHONE = "phone", _("Phone")
        REFERRAL = "referral", _("Referral")
        SOCIAL = "social", _("Social media")
        WHATSAPP = "whatsapp", _("WhatsApp")
        IMPORT = "import", _("Import")
        OTHER = "other", _("Other")

    class PreferredChannel(models.TextChoices):
        NONE = "none", _("None")
        EMAIL = "email", _("Email")
        SMS = "sms", _("SMS")
        WHATSAPP = "whatsapp", _("WhatsApp")
        PHONE = "phone", _("Phone")

    name = models.CharField(_("name"), max_length=200)
    email = models.CharField(_("email"), max_length=254, blank=True)
    # E.164 (``+34600111222``) or empty: every write goes through apps.customer.phones.
    phone = models.CharField(_("phone"), max_length=16, blank=True)
    tax_id = models.CharField(_("tax ID"), max_length=32, blank=True)
    company_name = models.CharField(_("company"), max_length=200, blank=True)
    address = models.CharField(_("address"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    # ISO 3166-1 alpha-2 (``ES``) or empty.
    country = models.CharField(_("country"), max_length=2, blank=True)
    # The picture's address (a URL), as the product keeps it.
    avatar = models.CharField(_("avatar"), max_length=500, blank=True)
    birthday = models.DateField(_("birthday"), null=True, blank=True)
    anniversary = models.DateField(_("anniversary"), null=True, blank=True)
    source = models.CharField(
        _("source"), max_length=16, choices=Source.choices, default=Source.WALK_IN
    )
    lifecycle_stage = models.CharField(
        _("stage"), max_length=16, choices=Stage.choices, default=Stage.LEAD
    )
    preferred_channel = models.CharField(
        _("preferred channel"),
        max_length=16,
        choices=PreferredChannel.choices,
        default=PreferredChannel.NONE,
    )
    notes = models.TextField(_("internal notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    total_purchases = models.PositiveIntegerField(_("purchases"), default=0)
    total_spent = models.BigIntegerField(_("spent (cents)"), default=0)
    last_purchase_at = models.DateTimeField(_("last purchase"), null=True, blank=True)
    # Name, email, phone, tax id and company, lowercased and without accents (apps.customer.search).
    search_text = models.TextField(_("search text"), blank=True, editable=False)
    groups = models.ManyToManyField(
        CustomerGroup, related_name="customers", blank=True, verbose_name=_("groups")
    )
    tags = models.ManyToManyField(
        CustomerTag, related_name="customers", blank=True, verbose_name=_("tags")
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absorbed",
        verbose_name=_("merged into"),
    )
    erased_at = models.DateTimeField(
        _("personal data erased at"), null=True, blank=True
    )

    objects = CustomerQuerySet.as_manager()

    class Meta:
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        # The order of customer.customer.list by default: by name, id as the tie-break.
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["name", "id"], name="customer_name_idx"),
            models.Index(fields=["phone"], name="customer_phone_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        """Keeps ``search_text`` in step with the fields it is built from, also on partial saves."""
        self.search_text = searchable(
            *(getattr(self, field) for field in SEARCHED_FIELDS)
        )
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "search_text" not in update_fields:
            kwargs["update_fields"] = [*update_fields, "search_text"]
        super().save(*args, **kwargs)


class CustomField(UUIDModel):
    """A field of the business's own on every card (CUSTOMER-F29); its values are text."""

    class FieldType(models.TextChoices):
        TEXT = "text", _("Text")
        NUMBER = "number", _("Number")
        DATE = "date", _("Date")
        BOOLEAN = "boolean", _("Yes/No")
        SELECT = "select", _("Select")
        TEXTAREA = "textarea", _("Long text")

    name = models.CharField(_("name"), max_length=100)
    field_type = models.CharField(
        _("type"), max_length=16, choices=FieldType.choices, default=FieldType.TEXT
    )
    # The choices of a ``select`` field; empty for the other types.
    options = models.JSONField(_("options"), default=list, blank=True)
    is_required = models.BooleanField(_("required"), default=False)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    # An inactive field is not shown on the cards nor required; its values stay.
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("custom field")
        verbose_name_plural = _("custom fields")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(is_active=True),
                name="customer_field_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class CustomFieldValue(UUIDModel):
    """A card's value of a custom field; an empty value is no row."""

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="field_values",
        verbose_name=_("customer"),
    )
    field = models.ForeignKey(
        CustomField,
        on_delete=models.CASCADE,
        related_name="values",
        verbose_name=_("field"),
    )
    value = models.TextField(_("value"))

    class Meta:
        verbose_name = _("custom field value")
        verbose_name_plural = _("custom field values")
        ordering = ["field__sort_order", "field__name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "field"], name="customer_field_value_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.field}: {self.value}"


class Activity(UUIDModel):
    """One entry of a card's timeline. A note IS its entry (``note_added``), as in Odoo's chatter.

    For the entries of this app ``kind`` is a key the screens translate: no sentence of the
    interface is stored. Another app writing through ``customer.activity.add`` brings its own key
    (``appointment.visit``) and its own ``title``.
    """

    class Kind(models.TextChoices):
        NOTE_ADDED = "note_added", _("Note added")
        PURCHASE_RECORDED = "purchase_recorded", _("Purchase recorded")
        PURCHASE_VOIDED = "purchase_voided", _("Purchase voided")
        PURCHASE_REFUNDED = "purchase_refunded", _("Purchase refunded")
        CONSENT_GRANTED = "consent_granted", _("Consent given")
        CONSENT_WITHDRAWN = "consent_withdrawn", _("Consent withdrawn")
        MERGED = "merged", _("Duplicate customer merged into this one")
        ERASED = "erased", _("Personal data erased")
        HEALTH_CONSENT_GRANTED = (
            "health_consent_granted",
            _("Permission to keep health data given"),
        )
        HEALTH_CONSENT_WITHDRAWN = (
            "health_consent_withdrawn",
            _("Permission to keep health data withdrawn: health data erased"),
        )
        HEALTH_UPDATED = "health_updated", _("Health data updated")

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="activity",
        verbose_name=_("customer"),
    )
    kind = models.CharField(_("kind"), max_length=40, choices=Kind.choices)
    title = models.CharField(_("title"), max_length=200, blank=True)
    # The note, the consent's words or the reason of a void or an erasure.
    text = models.TextField(_("text"), blank=True)
    data = models.JSONField(_("data"), default=dict, blank=True)
    # What the entry points at: the sale, the consent fact or the merged card, and its type.
    related_id = models.CharField(_("related id"), max_length=64, blank=True)
    related_type = models.CharField(_("related type"), max_length=40, blank=True)
    actor = models.CharField(_("by"), max_length=128, blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("activity")
        verbose_name_plural = _("activity")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["customer", "-created_at", "-id"], name="customer_activity_idx"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} ({self.created_at:%Y-%m-%d})"


class Purchase(UUIDModel):
    """One sale of a card (CUSTOMER-F20): recorded once, voided at most once, never deleted.

    A refund of it (CUSTOMER-F22) is a line of its own: the same sale, its refund's id, the amount
    returned as a negative amount and the status «refunded»; recorded once per refund.
    """

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", _("Paid")
        VOIDED = "voided", _("Voided")
        REFUNDED = "refunded", _("Refund")

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="purchases",
        verbose_name=_("customer"),
    )
    # The sale's id in the sale app (an opaque reference, no foreign key between apps); empty for a
    # manual entry, which is never deduplicated (NULLs are distinct in Postgres).
    sale_id = models.UUIDField(_("sale"), null=True, blank=True)
    # The refund's id in the sale app, on a refund line only.
    refund_id = models.UUIDField(_("refund"), null=True, blank=True)
    amount = models.BigIntegerField(_("amount (cents)"))
    currency = models.CharField(_("currency"), max_length=3, blank=True)
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.CONFIRMED
    )
    recorded_at = models.DateTimeField(_("purchased at"), default=timezone.now)
    voided_at = models.DateTimeField(_("voided at"), null=True, blank=True)
    void_reason = models.TextField(_("void reason"), blank=True)

    class Meta:
        verbose_name = _("purchase")
        verbose_name_plural = _("purchases")
        ordering = ["-recorded_at", "-id"]
        constraints = [
            # One paid line per sale; its refunds are lines of their own, one per refund.
            models.UniqueConstraint(
                fields=["sale_id"],
                condition=models.Q(refund_id__isnull=True),
                name="customer_purchase_sale_unique",
            ),
            models.UniqueConstraint(
                fields=["refund_id"], name="customer_purchase_refund_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sale_id or self.pk} ({self.get_status_display()})"


class Consent(UUIDModel):
    """One consent fact (CUSTOMER-F14, F15): rows are only added; a channel's state is its last fact."""

    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        SMS = "sms", _("SMS")
        WHATSAPP = "whatsapp", _("WhatsApp")
        PHONE = "phone", _("Phone")
        POSTAL = "postal", _("Post")

    class State(models.TextChoices):
        GRANTED = "granted", _("Given")
        WITHDRAWN = "withdrawn", _("Withdrawn")

    class Source(models.TextChoices):
        COUNTER = "counter", _("At the counter")
        WEB_FORM = "web_form", _("Web form")
        PHONE = "phone", _("By phone")
        EMAIL = "email", _("By email")
        IMPORT = "import", _("Imported")
        RECEIPT = "receipt", _("On the receipt")

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="consents",
        verbose_name=_("customer"),
    )
    # What it is for: marketing unless the business asks for something else.
    purpose = models.CharField(_("purpose"), max_length=40, default="marketing")
    # Empty for a permission that is not about reaching the person: health data (CUSTOMER-F32).
    channel = models.CharField(
        _("channel"), max_length=12, choices=Channel.choices, blank=True
    )
    state = models.CharField(_("state"), max_length=12, choices=State.choices)
    # The address it was given for, as it was then (an email, a phone, a postal address).
    contact_point = models.CharField(_("address"), max_length=255, blank=True)
    source = models.CharField(
        _("source"), max_length=12, choices=Source.choices, default=Source.COUNTER
    )
    # The exact words shown, stored verbatim, and their version.
    notice_text = models.TextField(_("notice"), blank=True)
    notice_version = models.CharField(_("notice version"), max_length=60, blank=True)
    evidence = models.CharField(_("evidence"), max_length=500, blank=True)
    reason = models.CharField(_("reason"), max_length=500, blank=True)
    recorded_by = models.CharField(_("recorded by"), max_length=128, blank=True)
    # When the person said it, which may be before it was typed.
    occurred_at = models.DateTimeField(_("occurred at"), default=timezone.now)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("consent")
        verbose_name_plural = _("consents")
        ordering = ["-occurred_at", "-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["customer", "purpose", "channel", "-occurred_at"],
                name="customer_consent_idx",
            ),
        ]

    def __str__(self) -> str:
        # A fact without channel (health data, CUSTOMER-F32) reads by its purpose.
        return f"{self.get_channel_display() or self.purpose}: {self.get_state_display()}"


class HealthRecord(UUIDModel):
    """A card's health data (CUSTOMER-F32): allergies and the last sensitivity test, one row per card.

    Special category data (GDPR art. 9): only written while the card's last ``health`` consent fact is
    a grant, deleted when it is withdrawn and when the card is erased. No other read carries it.
    """

    class TestResult(models.TextChoices):
        NEGATIVE = "negative", _("Negative")
        POSITIVE = "positive", _("Positive")

    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="health",
        verbose_name=_("customer"),
    )
    allergies = models.TextField(_("allergies and sensitivities"), blank=True)
    sensitivity_test_on = models.DateField(
        _("sensitivity test date"), null=True, blank=True
    )
    sensitivity_test_result = models.CharField(
        _("result"), max_length=12, choices=TestResult.choices, blank=True
    )
    updated_at = models.DateTimeField(_("updated at"), default=timezone.now)
    updated_by = models.CharField(_("updated by"), max_length=128, blank=True)

    class Meta:
        verbose_name = _("health record")
        verbose_name_plural = _("health records")

    def __str__(self) -> str:
        return str(self.customer_id)


class OrderLink(UUIDModel):
    """Which customer an open order has (CUSTOMER-F19): at most one per order."""

    # The order's id in the sale app: an opaque reference, no foreign key between apps.
    order_id = models.UUIDField(_("order"))
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name=_("customer"),
    )
    linked_at = models.DateTimeField(_("linked at"), default=timezone.now)

    class Meta:
        verbose_name = _("order link")
        verbose_name_plural = _("order links")
        ordering = ["-linked_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order_id"], name="customer_order_link_unique"
            )
        ]

    def __str__(self) -> str:
        return str(self.order_id)

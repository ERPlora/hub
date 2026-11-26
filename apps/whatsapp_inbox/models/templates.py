"""The copy of the business's message templates and the files of their headers, with what the Hub's form makes
and what its sending fills."""

import re

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


#: The buttons the Hub writes and sends as they are (no value to fill when sending).
HUB_BUTTONS = frozenset({"QUICK_REPLY", "URL", "PHONE_NUMBER"})
#: A variable that is not ``{{1}}``, ``{{2}}``…: one Meta names (``{{nombre}}``), which the Hub never fills.
NAMED_VARIABLE = re.compile(r"\{\{(?!\s*\d+\s*\}\})")


#: The headers that carry a file: a photo, a video or a document.
FILE_HEADERS = ("IMAGE", "VIDEO", "DOCUMENT")


def hub_writes(row) -> bool:
    """Whether the Hub's form makes this content: what its sending fills (``supported``), a header with a file only
    when that file was chosen here (``header_sample``; one made in WhatsApp Manager is changed there)."""
    if row.header_format in FILE_HEADERS:
        return row.supported and row.header_sample_id is not None
    return row.supported


def hub_handles(category: str, header_format: str, header: str, body: str, buttons: list) -> bool:
    """Whether the Hub's sending fills this content: no authentication code, no place header, a header of text
    without variables or of a file (sent with the file chosen), only numbered variables in the body, and only quick
    replies, fixed links and calls."""
    if category == "AUTHENTICATION" or header_format not in ("", "TEXT", *FILE_HEADERS) or "{{" in (header or ""):
        return False
    if NAMED_VARIABLE.search(body or ""):
        return False
    return all(
        isinstance(button, dict)
        and button.get("type") in HUB_BUTTONS
        and "{{" not in str(button.get("url", ""))
        for button in buttons or []
    )


class TemplateSample(UUIDModel):
    """The file of a template's header with a photo, a video or a document (WHATSAPP_INBOX-F29), kept in the hub file
    store at ``key`` (``samples.sample_key``: named by its content, so two rows may share one object). Meta reviews
    the template with it: its hand-over to erplora.com (door 8) carries it every time. Rows are never deleted: a
    template, its edit waiting in ``draft`` or a hand-over on its way may still name one.

    Each business keeps its samples in its own database."""

    class Kind(models.TextChoices):
        IMAGE = "IMAGE", pgettext_lazy("whatsapp template header", "Image")
        VIDEO = "VIDEO", pgettext_lazy("whatsapp template header", "Video")
        DOCUMENT = "DOCUMENT", pgettext_lazy("whatsapp template header", "Document")

    header_format = models.CharField(_("header type"), max_length=10, choices=Kind.choices)
    key = models.CharField(_("file in the store"), max_length=255, editable=False)
    sha256 = models.CharField(_("sha256"), max_length=64, editable=False)
    content_type = models.CharField(_("type"), max_length=64)
    size = models.PositiveBigIntegerField(_("size in bytes"))
    # The name it was chosen with, as Meta shows it in the review.
    name = models.CharField(_("name"), max_length=255)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("template header file")
        verbose_name_plural = _("template header files")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.name


class Template(UUIDModel):
    """A message template of the business's WhatsApp account: made and changed here (WHATSAPP_INBOX-F29…F31)
    or in WhatsApp Manager, and kept in step with what Meta holds (synced by the SaaS, F27, F28).

    The main fields are what Meta has (or, while Meta never had it, what was written here). An edit of a
    template Meta has waits in ``draft`` until erplora.com registers it, so the approved one stays usable and
    Meta's verdict never lands on a text changed afterwards. ``submit_state`` follows the hand-over to
    erplora.com (door 8) as a message's status does; a template deleted here keeps its row (``deleted_at``) so
    Meta's next list never brings it back, and ``delete_state`` follows its deletion at Meta (door 9).

    Each business keeps its templates in its own database.
    """

    class Category(models.TextChoices):
        UTILITY = "UTILITY", pgettext_lazy("whatsapp template", "Utility")
        MARKETING = "MARKETING", pgettext_lazy("whatsapp template", "Marketing")
        AUTHENTICATION = "AUTHENTICATION", pgettext_lazy("whatsapp template", "Authentication")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", pgettext_lazy("whatsapp template", "Not sent to Meta")
        APPROVED = "APPROVED", pgettext_lazy("whatsapp template", "Approved")
        PENDING = "PENDING", pgettext_lazy("whatsapp template", "In review")
        REJECTED = "REJECTED", pgettext_lazy("whatsapp template", "Rejected")
        PAUSED = "PAUSED", pgettext_lazy("whatsapp template", "Paused by Meta")
        DISABLED = "DISABLED", pgettext_lazy("whatsapp template", "Disabled by Meta")
        DELETED = "DELETED", _("Deleted in WhatsApp Manager")

    class HeaderFormat(models.TextChoices):
        NONE = "", pgettext_lazy("whatsapp template header", "None")
        TEXT = "TEXT", pgettext_lazy("whatsapp template header", "Text")
        IMAGE = "IMAGE", pgettext_lazy("whatsapp template header", "Image")
        VIDEO = "VIDEO", pgettext_lazy("whatsapp template header", "Video")
        DOCUMENT = "DOCUMENT", pgettext_lazy("whatsapp template header", "Document")
        LOCATION = "LOCATION", pgettext_lazy("whatsapp template header", "Location")

    class SubmitState(models.TextChoices):
        # The hand-over of a new template or an edit to erplora.com (door 8).
        NONE = "", _("Nothing to send to Meta")
        QUEUED = "queued", pgettext_lazy("whatsapp template", "Queued")
        SENDING = "sending", pgettext_lazy("whatsapp template", "Sending to Meta")
        FAILED = "failed", pgettext_lazy("whatsapp template", "Not accepted")

    class DeleteState(models.TextChoices):
        NONE = "", _("Not deleted")
        PENDING = "pending", _("Being deleted at Meta")
        DONE = "done", _("Deleted")

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
    header_format = models.CharField(
        _("header type"), max_length=10, choices=HeaderFormat.choices, default=HeaderFormat.NONE, blank=True
    )
    header = models.CharField(_("header"), max_length=200, blank=True)
    # The file of a photo, video or document header chosen here: Meta reviews the template with it (one made in
    # WhatsApp Manager has none, and is changed there).
    header_sample = models.ForeignKey(
        TemplateSample,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("header file"),
    )
    body = models.TextField(_("body"), blank=True)
    # An example of each body variable, in order: Meta reviews the template with them.
    body_examples = models.JSONField(_("examples of the variables"), default=list, blank=True)
    footer = models.CharField(_("footer"), max_length=200, blank=True)
    # Meta's buttons as it lists them: ``{"type", "text", "url"?, "phone_number"?}``.
    buttons = models.JSONField(_("buttons"), default=list, blank=True)
    # How many variables the body takes ({{1}}…{{n}}).
    variables = models.PositiveSmallIntegerField(_("variables"), default=0)
    rejected_reason = models.CharField(_("Meta's reason"), max_length=500, blank=True)
    meta_id = models.CharField(_("Meta id"), max_length=64, blank=True)
    synced_at = models.DateTimeField(pgettext_lazy("whatsapp template", "synced at"), null=True, blank=True)
    # An edit of a template Meta has, waiting for erplora.com to register it (category, header_format, header,
    # header_sample, body, body_examples, footer, buttons); empty when there is none.
    draft = models.JSONField(_("changes not yet at Meta"), null=True, blank=True)
    submit_state = models.CharField(
        _("sending to Meta"), max_length=10, choices=SubmitState.choices, default=SubmitState.NONE, blank=True
    )
    # The key the Hub sends with this hand-over (Idempotency-Key): a retry never registers it twice.
    submit_key = models.UUIDField(_("send key"), null=True, blank=True)
    # The code of the last hand-over or deletion that did not end well and, only for a refusal of Meta's the Hub has
    # no name for, Meta's reason as it came: the Hub's words are said when it is read (queries.reasons.template_reason).
    submit_error_code = models.CharField(_("error code"), max_length=64, blank=True)
    submit_error = models.CharField(_("error"), max_length=500, blank=True)
    submit_at = models.DateTimeField(_("handed over at"), null=True, blank=True)
    deleted_at = models.DateTimeField(pgettext_lazy("whatsapp template", "deleted at"), null=True, blank=True)
    delete_state = models.CharField(
        _("deletion at Meta"), max_length=10, choices=DeleteState.choices, default=DeleteState.NONE, blank=True
    )
    # Whether the Hub makes and sends what Meta holds (``hub_handles``); else only WhatsApp Manager does.
    supported = models.BooleanField(_("handled by the Hub"), default=True, editable=False)

    class Meta:
        verbose_name = _("template")
        verbose_name_plural = _("templates")
        ordering = ["name", "language", "id"]
        constraints = [
            # One live template per name and language: one deleted here frees them. In the database it still holds
            # the old business column (``migrations/0012``), where every row the code writes has it empty.
            models.UniqueConstraint(
                fields=["name", "language"],
                condition=Q(deleted_at__isnull=True),
                name="whatsapp_inbox_template_live_host_name_language_unique",
            ),
            models.UniqueConstraint(
                fields=["submit_key"],
                condition=Q(submit_key__isnull=False),
                name="whatsapp_inbox_template_submit_key_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.language})"

    def save(self, *args, **kwargs):
        self.supported = hub_handles(self.category, self.header_format, self.header, self.body, self.buttons)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = {*update_fields, "supported"}
        super().save(*args, **kwargs)

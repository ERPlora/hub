"""Models of the website app: the business's site (one row) and the images uploaded for it.

``Site`` holds the draft the owner edits (``template``, ``theme``, ``content``) and what visitors see
(``published_content``: the template, theme and content of the last publication, with the catalog's snapshot), so a
change of the draft never reaches the public page until it is published. ``published_version`` goes up on every
publication and names the cached HTML (``public_home``). ``is_live`` says whether ``/`` shows it.

The business's database holds its one site (``singleton``) and its own images: no row says whose it is. The images'
keys and the cache keys carry the hub, for the file store and the cache, which every business shares.
"""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext, pgettext_lazy
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128


class Site(UUIDModel):
    class Template(models.TextChoices):
        CLASSIC = "classic", _("Classic")
        MODERN = "modern", _("Modern")
        MINIMAL = "minimal", _("Minimal")
        BOLD = "bold", _("Bold")

    singleton = models.BooleanField(_("single row"), default=True, db_default=True, editable=False)
    template = models.CharField(_("template"), max_length=16, choices=Template.choices, default=Template.CLASSIC)
    theme = models.JSONField(_("theme"), default=dict, blank=True)
    content = models.JSONField(_("content"), default=dict, blank=True)
    published_content = models.JSONField(_("published content"), default=dict, blank=True)
    published_version = models.PositiveIntegerField(_("published version"), default=0)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    is_live = models.BooleanField(_("live"), default=False)
    #: Google's last good answer for the reviews section's place (``apps.website.reviews``): it stands in for the
    #: cache when it was flushed or Google fails, for 30 days at most.
    reviews_snapshot = models.JSONField(_("Google reviews"), default=dict, blank=True, db_default={})
    #: Said with the app's context, like ``created_at`` of ``Image``: the site and its images are feminine in Spanish
    #: («actualizada el», like its «publicada el»), where Demo and Clientes, loaded before, say it masculine.
    updated_at = models.DateTimeField(pgettext_lazy("website", "updated at"), auto_now=True)
    updated_by = models.CharField(pgettext_lazy("website", "updated by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("website")
        verbose_name_plural = _("websites")
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="website_site_single_row"),
            models.CheckConstraint(condition=Q(singleton=True), name="website_site_singleton"),
            models.CheckConstraint(
                condition=Q(template__in=["classic", "modern", "minimal", "bold"]), name="website_site_template_valid"
            ),
        ]

    def __str__(self) -> str:
        # Not plain gettext: Clientes, loaded before, says a customer's «Website» as «Web».
        return pgettext("website", "Website")


class Image(UUIDModel):
    """An image uploaded for the business's site, kept in ``storages["hub_files"]`` under its hub and content hash."""

    key = models.CharField(_("key"), max_length=255, unique=True)
    sha256 = models.CharField(_("SHA-256"), max_length=64)
    content_type = models.CharField(_("content type"), max_length=32)
    width = models.PositiveIntegerField(_("width"))
    height = models.PositiveIntegerField(_("height"))
    size = models.PositiveIntegerField(_("size"))
    # The name of the file it was first uploaded with (the same bytes again are the same image): what the assistant's
    # card calls it. Empty for an upload of before.
    filename = models.CharField(_("file name"), max_length=200, blank=True, default="", db_default="")
    created_at = models.DateTimeField(pgettext_lazy("website", "created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("image")
        verbose_name_plural = _("images")
        ordering = ["-created_at", "id"]

    def __str__(self) -> str:
        return self.key

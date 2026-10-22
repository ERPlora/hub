"""Models of the website app: the site (one row per hub) and the images uploaded for it.

``Site`` holds the draft the owner edits (``template``, ``theme``, ``content``) and what visitors see
(``published_content``: the template, theme and content of the last publication, with the catalog's snapshot), so a
change of the draft never reaches the public page until it is published. ``published_version`` goes up on every
publication and names the cached HTML (``public_home``). ``is_live`` says whether ``/`` shows it.

Phase 1 has no tenancy (PLAN §29): the tables are shared by every hub until phase 2 moves them to each hub's
database, so each row names its hub in ``hub_id``, the registry's ``Hub.id`` (``base.operations.hub_id``; no foreign
key: the registry lives in the control database from phase 2). A hub has one site, and the operations and ``/`` only
ever read and write the request hub's rows. In phase 2 each hub's database holds its one site and its own images,
and the column stays, always the same value. The images' keys and the cache keys carry the hub too.
"""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128


class Site(UUIDModel):
    class Template(models.TextChoices):
        CLASSIC = "classic", _("Classic")
        MODERN = "modern", _("Modern")
        MINIMAL = "minimal", _("Minimal")
        BOLD = "bold", _("Bold")

    hub_id = models.UUIDField(_("hub"), unique=True, editable=False)
    template = models.CharField(_("template"), max_length=16, choices=Template.choices, default=Template.CLASSIC)
    theme = models.JSONField(_("theme"), default=dict, blank=True)
    content = models.JSONField(_("content"), default=dict, blank=True)
    published_content = models.JSONField(_("published content"), default=dict, blank=True)
    published_version = models.PositiveIntegerField(_("published version"), default=0)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    is_live = models.BooleanField(_("live"), default=False)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(_("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("website")
        verbose_name_plural = _("websites")
        constraints = [
            models.CheckConstraint(
                condition=Q(template__in=["classic", "modern", "minimal", "bold"]), name="website_site_template_valid"
            ),
        ]

    def __str__(self) -> str:
        return str(_("Website"))


class Image(UUIDModel):
    """An image uploaded for a hub's site, kept in ``storages["hub_files"]`` under its hub and content hash."""

    hub_id = models.UUIDField(_("hub"), db_index=True, editable=False)
    key = models.CharField(_("key"), max_length=255, unique=True)
    sha256 = models.CharField(_("SHA-256"), max_length=64)
    content_type = models.CharField(_("content type"), max_length=32)
    width = models.PositiveIntegerField(_("width"))
    height = models.PositiveIntegerField(_("height"))
    size = models.PositiveIntegerField(_("size"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("image")
        verbose_name_plural = _("images")
        ordering = ["-created_at", "id"]

    def __str__(self) -> str:
        return self.key

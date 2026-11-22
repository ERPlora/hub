"""How a person appears in this hub and what they prefer: «My profile»."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


class Profile(UUIDModel):
    """How a person appears in this hub and what they prefer: «My profile».

    The name and the contact email are this business's (receipts, Personal), not the erplora.com account's, which
    the SaaS keeps; the contact email never gives nor takes any access. ``language``, ``theme_mode`` and ``palette``
    empty = the business's. ``ui_scale`` is the percentage painted across the whole interface.
    """

    class Language(models.TextChoices):
        BUSINESS = "", _("The business's language")
        SPANISH = "es", "Español"
        ENGLISH = "en", "English"

    class ThemeMode(models.TextChoices):
        BUSINESS = "", _("The business's appearance")
        SYSTEM = "system", _("System")
        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")

    class Palette(models.TextChoices):
        """The palettes of «My profile», by the names it shows them."""

        BUSINESS = "", pgettext_lazy("palette", "The business's palette")
        ERPLORA = "erplora", "ERPlora"
        TERRACOTTA = "terracotta", pgettext_lazy("palette", "Terracotta")
        CORPORATE = "corporate", pgettext_lazy("palette", "Corporate")
        MINIMAL = "minimal", pgettext_lazy("palette", "Minimal")
        FOREST = "forest", pgettext_lazy("palette", "Forest")
        OCEAN = "ocean", pgettext_lazy("palette", "Ocean")
        VIOLET = "violet", pgettext_lazy("palette", "Violet")

    class UiScale(models.IntegerChoices):
        PERCENT_80 = 80, "80%"
        PERCENT_90 = 90, "90%"
        PERCENT_100 = 100, "100%"
        PERCENT_110 = 110, "110%"
        PERCENT_120 = 120, "120%"

    username = models.CharField(_("person"), max_length=150, unique=True)
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    contact_email = models.EmailField(_("contact email"), blank=True)
    avatar = models.CharField(_("photo"), max_length=255, blank=True)
    language = models.CharField(_("language"), max_length=8, choices=Language.choices, blank=True)
    theme_mode = models.CharField(_("appearance"), max_length=8, choices=ThemeMode.choices, blank=True)
    palette = models.CharField(_("palette"), max_length=16, choices=Palette.choices, blank=True)
    ui_scale = models.PositiveSmallIntegerField(
        _("interface scale"), choices=UiScale.choices, default=100, db_default=100
    )
    updated_at = models.DateTimeField(pgettext_lazy("profile", "updated at"), auto_now=True)

    class Meta:
        verbose_name = _("profile")
        verbose_name_plural = _("profiles")

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.username

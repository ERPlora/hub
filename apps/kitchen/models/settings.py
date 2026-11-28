"""The kitchen display settings: one row."""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.kitchen.models.fields import ACTOR_MAX_LENGTH, OrderType, _in

MIN_MINUTES = 1
MAX_MINUTES = 120
MAX_VOLUME = 100


class SoundTone(models.TextChoices):
    CHIME = "chime", _("Chime")
    BELL = "bell", _("Bell")
    BUZZER = "buzzer", _("Buzzer")


class KitchenSettings(UUIDModel):
    """The kitchen display settings: one row, made with the app's tables (migration 0002)."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    show_timer = models.BooleanField(_("show timer"), default=True)
    warning_minutes = models.PositiveSmallIntegerField(
        _("amber warning (minutes)"), default=15
    )
    critical_minutes = models.PositiveSmallIntegerField(
        _("red alert (minutes)"), default=30
    )
    color_coding = models.BooleanField(_("colour semaphore"), default=True)
    sound_enabled = models.BooleanField(_("sound on a new ticket"), default=True)
    sound_volume = models.PositiveSmallIntegerField(_("sound volume"), default=70)
    sound_tone = models.CharField(
        _("sound tone"),
        max_length=8,
        choices=SoundTone.choices,
        default=SoundTone.CHIME,
    )
    print_pass = models.BooleanField(
        _("print the pass when marked ready"), default=False
    )
    works_from_screen = models.BooleanField(
        _("the kitchen works from the screen"), default=True
    )
    #: When «works from the screen» last changed: charging only serves by paper what closed after it.
    screen_changed_at = models.DateTimeField(
        _("screen mode changed at"), null=True, blank=True
    )
    default_order_type = models.CharField(
        _("default order type"),
        max_length=10,
        choices=OrderType.choices,
        default=OrderType.DINE_IN,
    )
    #: The kitchen receives the rounds fired from this moment on (when its tables were made).
    receiving_since = models.DateTimeField(_("receiving since"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("kitchen settings")
        verbose_name_plural = _("kitchen settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="kitchen_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="kitchen_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(
                    warning_minutes__gte=MIN_MINUTES, warning_minutes__lte=MAX_MINUTES
                ),
                name="kitchen_settings_warning_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    critical_minutes__gte=MIN_MINUTES, critical_minutes__lte=MAX_MINUTES
                ),
                name="kitchen_settings_critical_range",
            ),
            models.CheckConstraint(
                condition=Q(warning_minutes__lt=models.F("critical_minutes")),
                name="kitchen_settings_amber_first",
            ),
            models.CheckConstraint(
                condition=Q(sound_volume__lte=MAX_VOLUME),
                name="kitchen_settings_volume",
            ),
            models.CheckConstraint(
                condition=_in("sound_tone", SoundTone), name="kitchen_settings_tone"
            ),
            models.CheckConstraint(
                condition=_in("default_order_type", OrderType),
                name="kitchen_settings_type",
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)

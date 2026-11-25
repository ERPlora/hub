"""Whether each module is on in a business (``base.activation``)."""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


class AppActivation(UUIDModel):
    """Whether a module is on in a business, and whether the business chose it (the rules: ``base.activation``).

    ``chosen`` is what the plan's ``max_apps`` counts: an app the business turned on itself, never one the closure by
    ``requires`` brought along. A business without any row has every module off (the baseline): its first change
    writes them all down. The hubs made before that baseline have every module on, its roots chosen (migration 0017).
    ``host`` is the business's slug (the scope's key, as ``Membership`` and the outbox keep it). The rows of a business
    that takes another address are written down under that one (``base.services.address_change``); its database may hold
    those of its former ones, and of other businesses if its cut copied the database they shared: they are none of its.

    In a hub with its own database an app's tables are made the first time it is turned on: the row is
    ``creating`` until the worker made them (``on``), or ``failed`` with ``attempts``, ``last_error`` and
    ``next_attempt_at`` (tried again then, or by hand); ``target`` is the app's last migration in the code that asked,
    so a worker of an older code (a deploy rolling) leaves it to one of that code. The tables of an app off are never
    dropped.
    """

    class State(models.TextChoices):
        ON = "on", pgettext_lazy("app state", "On")
        OFF = "off", pgettext_lazy("app state", "Off")
        CREATING = "creating", pgettext_lazy("app state", "Turning on")
        FAILED = "failed", pgettext_lazy("app state", "Could not turn on")

    host = models.CharField(_("host"), max_length=63, help_text=_("The hub's slug."))
    app = models.CharField(pgettext_lazy("app activation", "app"), max_length=100)
    state = models.CharField(pgettext_lazy("app activation", "state"), max_length=16, choices=State.choices)
    chosen = models.BooleanField(
        pgettext_lazy("app activation", "chosen"),
        default=False,
        help_text=pgettext_lazy(
            "app activation", "Turned on by the business itself; what came along with another app is not."
        ),
    )
    changed_at = models.DateTimeField(pgettext_lazy("app activation", "changed at"), auto_now=True)
    attempts = models.PositiveIntegerField(
        pgettext_lazy("app activation", "attempts"),
        default=0,
        db_default=0,
        help_text=pgettext_lazy("app activation", "How many times making its tables failed in a row."),
    )
    last_error = models.TextField(
        pgettext_lazy("app activation", "last error"),
        blank=True,
        default="",
        db_default="",
        help_text=pgettext_lazy("app activation", "Why making its tables failed the last time."),
    )
    next_attempt_at = models.DateTimeField(
        pgettext_lazy("app activation", "next attempt at"),
        null=True,
        blank=True,
        help_text=pgettext_lazy("app activation", "When the worker makes its tables again."),
    )
    target = models.CharField(
        pgettext_lazy("app activation", "target migration"),
        max_length=255,
        blank=True,
        default="",
        db_default="",
        help_text=pgettext_lazy(
            "app activation", "The last migration of the code that asked for its tables: an older worker leaves it."
        ),
    )

    class Meta:
        verbose_name = pgettext_lazy("app activation", "app activation")
        verbose_name_plural = pgettext_lazy("app activation", "app activations")
        ordering = ["host", "app"]
        constraints = [
            models.UniqueConstraint(fields=["host", "app"], name="base_appactivation_host_app"),
            models.CheckConstraint(
                condition=Q(state__in=["on", "off", "creating", "failed"]), name="base_appactivation_state"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.app} @ {self.host} ({self.state})"

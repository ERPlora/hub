"""The freeze of what changes a database's schema."""

from django.db import models
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


class Freeze(UUIDModel):
    """The freeze of what changes a database's schema, for a database upgrade with Blue/Green (logical
    replication copies no DDL). While ``frozen``, the worker makes, drops and moves no
    database and makes no app's tables (``base.worker``: what was asked waits in its queue and is done once it is
    lifted), and ``manage.py migrate_hubs`` refuses to start; the relay, the tasks and the sends to the AEAT go on.
    ``since`` and ``by`` say when and by whom it was last frozen or lifted; ``reason``, why it is frozen.

    One row at most (``control_freeze_one_row``), which control's migration makes; none is the same as never frozen.
    Written only by ``control.freeze.set`` (``control.services``), read by ``control.freeze.get``, the SaaS's signed
    status poll (``base.hub.get``) and, once a tick, by the worker (``control.queries.active_freeze``)."""

    frozen = models.BooleanField(pgettext_lazy("freeze", "frozen"), default=False)
    reason = models.CharField(pgettext_lazy("freeze", "reason"), max_length=500, blank=True, default="")
    since = models.DateTimeField(pgettext_lazy("freeze", "since"), null=True, blank=True)
    by = models.CharField(pgettext_lazy("freeze", "by"), max_length=150, blank=True, default="")

    class Meta:
        verbose_name = pgettext_lazy("freeze", "freeze")
        verbose_name_plural = pgettext_lazy("freeze", "freeze")
        constraints = [models.UniqueConstraint(models.Value(True), name="control_freeze_one_row")]

    def __str__(self) -> str:
        return str(pgettext_lazy("freeze", "frozen") if self.frozen else pgettext_lazy("freeze", "not frozen"))

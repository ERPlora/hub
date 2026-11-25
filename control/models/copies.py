"""The databases a move or a restore leaves or makes beside a hub's own, and what the staff asks the worker
to do with them."""

import datetime as dt

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from control.models.hubs import Cluster, Hub


class MovedCopy(UUIDModel):
    """The database a hub left behind on the server it moved from: its ``<control>_move_<hex>``
    (``base.tenancy.names``), closed to the app, kept a few days in case the move must be undone by hand, then dropped
    by the worker with its row (``base.tenancy.move``). ``cluster`` empty: the settings' own server. One per database
    name and server: a newer move off the same server replaces the older copy. A restore keeps the hub's database it
    replaced the same way (``<control>_old_<hex>``, its own UUIDv7; ``base.tenancy.restore``), one per restore.

    Written before the worker renames the hub's database, without ``moved_at`` while the move goes on: the hub's data
    is in that copy then, whatever else of that name the servers hold, so a move cut short is undone or gone on from it
    and never from a database that only has the name. ``moved_at`` is set when control switches the hub."""

    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="moved_copies", verbose_name=_("hub"))
    cluster = models.ForeignKey(
        Cluster,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="moved_copies",
        verbose_name=_("cluster"),
    )
    db_name = models.CharField(_("database"), max_length=63)
    moved_at = models.DateTimeField(_("moved at"), null=True, blank=True)
    # While the move goes on: the origin's schema record as control had it (the destination's is written when it is
    # migrated, ``migrator.schema.ensure_schema``), given back if the move is undone. Only the worker writes a note, right
    # before it renames: a note is always the truth of where the data is (a cancel never makes nor takes one).
    schema_state = models.CharField(_("schema"), max_length=16, blank=True, default="", db_default="")
    schema_apps = models.JSONField(_("created apps"), null=True, blank=True)

    class Meta:
        verbose_name = _("copy after a move")
        verbose_name_plural = _("copies after a move")
        ordering = ["moved_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cluster", "db_name"], name="control_movedcopy_one_per_server", nulls_distinct=False
            )
        ]

    def __str__(self) -> str:
        return self.db_name


class AskedOfTheWorker(UUIDModel):
    """What the staff asks of the worker in the Hub admin and the worker does under the row's own lease, never the
    hub's (a separate copy, a recovery from one): who asked it and when, why it failed last, and the lease
    (``lease_owner``, ``lease_until``) the worker holds while it works on it."""

    last_error = models.TextField(_("last error"), blank=True, default="", db_default="")
    asked_by = models.CharField(pgettext_lazy("separate copy", "asked by"), max_length=150)
    asked_at = models.DateTimeField(pgettext_lazy("separate copy", "asked at"), auto_now_add=True)
    lease_owner = models.CharField(_("leased by"), max_length=128, blank=True, default="", db_default="")
    lease_until = models.DateTimeField(_("leased until"), null=True, blank=True)

    class Meta:
        abstract = True


class RestoredCopy(AskedOfTheWorker):
    """A hub's database as it was at a moment, made aside on the hub's own cluster while the business goes on
    (BASE-F114): asked in the Hub admin (``control.hub.restore_aside``), made by the worker from the hub's copy
    on a temporary cluster (``base.tenancy.restore``, «restore aside»), then dropped with its row after
    ``move.worker_pass.MOVED_COPY_DAYS``. Its database, ``<control>_copy_<its hex>`` (``base.tenancy.names``), is no
    business: no hub's row names it, it is granted to none of the app's roles and no process registers an alias of it,
    so nothing in it ever reaches the tax authority. The business itself is never closed nor changed by it.

    ``source`` is the temporary cluster while the copy is to make (it cannot be deleted then), emptied once made or
    failed. ``cluster`` is where the copy is (empty: the settings' own server), which cannot be deleted while it is
    there. The worker holds the row's own lease (``lease_owner``, ``lease_until``) while it makes it, never the hub's:
    the business's own work does not wait for its copy."""

    class Status(models.TextChoices):
        COPYING = "copying", pgettext_lazy("separate copy", "Being made")
        MADE = "made", pgettext_lazy("separate copy", "Made")
        FAILED = "failed", pgettext_lazy("separate copy", "Failed")

    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="restored_copies", verbose_name=_("hub"))
    cluster = models.ForeignKey(
        Cluster,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="restored_copies",
        verbose_name=_("cluster"),
    )
    source = models.ForeignKey(
        Cluster,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="copies_made_from",
        verbose_name=pgettext_lazy("restore", "Temporary cluster"),
    )
    restore_point = models.DateTimeField(pgettext_lazy("restore", "Moment"))
    db_name = models.CharField(_("database"), max_length=63)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.COPYING, db_default=Status.COPYING
    )
    made_at = models.DateTimeField(pgettext_lazy("separate copy", "made at"), null=True, blank=True)

    class Meta:
        verbose_name = _("separate copy")
        verbose_name_plural = _("separate copies")
        ordering = ["-asked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cluster", "db_name"], name="control_restoredcopy_one_per_server", nulls_distinct=False
            )
        ]

    def __str__(self) -> str:
        # Its hub and its moment, words a phone wraps; its database's name is one piece of 40-odd characters.
        return f"{self.hub.slug} · {self.restore_point.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC"


class CopyRecovery(AskedOfTheWorker):
    """What the staff asked to bring back into a business from one of its separate copies (BASE-F114): asked in the Hub
    admin (``control.copy.recover``), done by the worker (``base.tenancy.recovery``), which reads the copy and, by each
    app's own operations, brings back in the business what it deleted and still holds and creates what it lacks. Dropped
    with its copy.

    ``apps`` are the labels asked, each an app that answers ``recoverable_from_copy`` on its ``LiveAppConfig``;
    ``language`` is the staff's, which the apps' refusals are said in. ``results`` says, for each thing each app
    declares it gives back (its ``label``, as the code writes it; absent from a result noted before each was counted
    apart, which is the app's whole, and from that of an app that declares nothing), how many were restored (absent
    from a result noted before that count existed), created and not, with why (``reasons``, the first
    :data:`REASONS_KEPT`, by the copy's id: no personal data), how many came back without something that hung from
    them and what (``noted`` and ``notes``, the same way; both absent while none did), or why it gave nothing back
    (``refused``). The worker holds the row's own lease (``lease_owner``, ``lease_until``) while it recovers, never
    the hub's: the business's own work does not wait for it."""

    #: How many reasons a recovery keeps, result by result, of the records its operation refuses, and how many notes of
    #: what the records it brought back came back without.
    REASONS_KEPT = 50

    class Status(models.TextChoices):
        ASKED = "asked", pgettext_lazy("recovery", "Asked")
        DONE = "done", pgettext_lazy("recovery", "Done")
        FAILED = "failed", pgettext_lazy("recovery", "Failed")

    copy = models.ForeignKey(
        RestoredCopy, on_delete=models.CASCADE, related_name="recoveries", verbose_name=_("separate copy")
    )
    apps = models.JSONField(pgettext_lazy("recovery", "what"), default=list)
    language = models.CharField(_("language"), max_length=16, default="en", db_default="en")
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.ASKED, db_default=Status.ASKED
    )
    results = models.JSONField(pgettext_lazy("recovery", "results"), default=list, blank=True)
    done_at = models.DateTimeField(pgettext_lazy("recovery", "done at"), null=True, blank=True)

    class Meta:
        verbose_name = _("recovery")
        verbose_name_plural = _("recoveries")
        ordering = ["-asked_at"]

    def __str__(self) -> str:
        return str(self.copy)


class LeftoverDatabase(UUIDModel):
    """A database a move may have left on its destination when it was undone without reaching it: the hub's
    name on that cluster, dropped by the worker on a later pass (``base.tenancy.move``)
    under the hub's lease, never while control says a hub's database is there (the hub on that cluster, moving to it,
    or living on the same server), and forgotten then."""

    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="leftovers", verbose_name=_("hub"))
    cluster = models.ForeignKey(
        Cluster, on_delete=models.PROTECT, related_name="leftovers", verbose_name=_("cluster")
    )
    db_name = models.CharField(_("database"), max_length=63)
    noted_at = models.DateTimeField(_("noted at"))

    class Meta:
        verbose_name = _("database left by an undone move")
        verbose_name_plural = _("databases left by undone moves")
        ordering = ["noted_at"]
        constraints = [
            models.UniqueConstraint(fields=["cluster", "db_name"], name="control_leftover_one_per_server")
        ]

    def __str__(self) -> str:
        return self.db_name

"""The jobs that wait and who there is to print them, per function and without operations: whether a device set up here
prints its receipts, and how many of its jobs no device can print."""

import datetime as dt

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.printing.models import PrintDevice, Printer, PrintJob

from .device_reads import active_devices, devices_on, signed_out_by_the_plan

#: A job that has waited this long with no device there to print it rings the bell: not every till that restarts
#: (the old hub's ``UNDRAINED_ALERT_SECONDS``).
STALLED_AFTER = dt.timedelta(seconds=60)

PENDING = Q(status=PrintJob.Status.PENDING)


def _takeable(devices: QuerySet[PrintDevice], usages: list[str]) -> tuple[set[tuple[str, str]], Q]:
    """What ``devices`` print: the (function, paper) of the active printers they reach, and the waiting jobs they take.

    A device prints the active printers it reaches: the jobs of those printers, and the jobs of a function no printer
    took yet on the paper of one of them (``printing.job.claim``).
    """
    reached = Printer.objects.filter(is_active=True, devices__in=devices)
    papers = {
        (usage, PrintJob.Format.A4 if kind == Printer.Kind.SYSTEM else PrintJob.Format.RECEIPT)
        for usage, kind in reached.filter(usage__in=usages).values_list("usage", "kind").distinct()
    }
    takeable = Q(printer__in=reached)
    for usage, paper in papers:
        takeable |= Q(printer__isnull=True, usage=usage, format=paper)
    return papers, takeable


def _waiting_for_nobody(usages: list[str], takeable: Q, since=None) -> dict[str, int]:
    """Per function, how many of its jobs wait (queued at ``since`` or before, if given) that ``takeable`` leaves."""
    jobs = PrintJob.objects.filter(PENDING, usage__in=usages)
    if since is not None:
        jobs = jobs.filter(created_at__lte=since)
    rows = jobs.values("usage").annotate(waiting=Count("id"), takeable=Count("id", filter=takeable))
    return {row["usage"]: row["waiting"] - row["takeable"] for row in rows}


def coverage(usages: list[str]) -> dict[str, tuple[bool, int]]:
    """Per function: whether a device set up here reaches an active printer of it on receipt paper, and how many of
    its jobs wait that no device set up here can print.

    Set up is enough, as the old hub's registration for a station: a device off right now is not a step undone, nor a
    device to set up (:func:`stalled` says whether it is on). Only waiting jobs count: one a device has is that
    device's, and one that ended waits for nobody.
    """
    papers, takeable = _takeable(active_devices(), usages)
    jobs = _waiting_for_nobody(usages, takeable)
    return {usage: ((usage, PrintJob.Format.RECEIPT) in papers, jobs.get(usage, 0)) for usage in usages}


def stalled(usages: list[str]) -> dict[str, int]:
    """Per function, the bell's «Nothing is printing»: its jobs that have waited :data:`STALLED_AFTER` or more and that
    no device there can print — one set up here whose last news is within :data:`SEEN_WITHIN` (the old hub's
    ``print_hosts::is_undrained``). A device set up but off prints nothing: nobody is printing its papers."""
    now = timezone.now()
    _papers, takeable = _takeable(devices_on(now), usages)
    jobs = _waiting_for_nobody(usages, takeable, since=now - STALLED_AFTER)
    return {usage: jobs.get(usage, 0) for usage in usages}


def signed_out_usages(usages: list[str]) -> set[str]:
    """The functions with an active printer that a device signed out by the plan's cap of devices reaches: when their
    jobs wait for nobody, that is why, and not a device switched off."""
    reached = Printer.objects.filter(is_active=True, usage__in=usages, devices__in=signed_out_by_the_plan())
    return set(reached.values_list("usage", flat=True))


def waits_for_device(job: PrintJob) -> bool:
    """Whether ``job`` waits in the queue with no device there to print it, as :func:`stalled` counts one but from the
    moment it is queued: nothing has printed it, and nothing will until such a device is set up or on."""
    _papers, takeable = _takeable(devices_on(timezone.now()), [job.usage])
    return PrintJob.objects.filter(PENDING, pk=job.pk).exclude(takeable).exists()

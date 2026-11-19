"""Whether a device is there to print now, and so whether the station of a function answers: the Home's health row and
System's «Your printer» read the same answer."""

import datetime as dt

from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

# The package's own helpers: it imports this module first, so they are read when the query runs.
from apps.printing import queries
from apps.printing.models import PrintJob
from apps.printing.schemas import CoverageIn
from apps.printing.schemas.health import DeviceHealthOut

#: A device set up here is there while its last news is this recent: its hello or a beat on base's /ws/print, asking for
#: a job or being set up from it (the old hub's ``HOST_TTL_SECONDS``: three missed beats of 30 s).
SEEN_WITHIN = dt.timedelta(seconds=90)


@operation(
    "printing.device.health",
    kind="query",
    permission="printing.view_settings",
    input=CoverageIn,
    output=DeviceHealthOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the receipt printer working right now?",
                "is the receipt station connected at the moment?",
            ),
            "es": (
                "¿funciona ahora mismo la impresora de tiques?",
                "¿está enchufada y conectada la impresora de los tiques?",
            ),
        },
        "description": "Whether the station of a function (receipt, kitchen, bar, label) answers right now: ok when a "
        "device set up to print it gave news in the last 90 s, no_signal when it is set up but quiet (the ERPlora app "
        "is closed or the device is off), not_configured when no device is set up to print it.",
    },
)
def device_health(ctx: OperationContext, params: CoverageIn) -> dict:
    usage = params.usage
    configured, _waiting = queries.coverage([usage])[usage]
    if not configured:
        return {"usage": usage, "state": "not_configured"}
    there = queries.active_devices().filter(last_seen_at__gte=timezone.now() - SEEN_WITHIN)
    papers, _takeable = queries._takeable(there, [usage])
    return {"usage": usage, "state": "ok" if (usage, PrintJob.Format.RECEIPT) in papers else "no_signal"}

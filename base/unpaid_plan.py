"""The bell's notice of a plan with an unpaid invoice, from erplora.com's photo of the business (``Hub.state``).

The photo says ``past_due`` while the invoice waits inside its grace, and ``suspends_on`` is the instant erplora.com
suspends the business. The Hub never asks erplora.com and never counts the grace itself: a photo without
``suspends_on`` gives a notice without a date.
"""

import datetime as dt
import logging
import math
from collections.abc import Mapping
from typing import Any

from django.utils import formats
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.meta import BellCounter

from base import bell
from base.auth import SAAS_PANEL_PATH, saas_url
from base.business import zone_of
from base.home.bell_counters import MIN_BELL_REFRESH_SECONDS
from control.models import Hub

logger = logging.getLogger(__name__)

PAST_DUE = "past_due"
#: The longest the bell waits to read itself again for a deadline: a browser's timer cannot wait much longer.
MAX_REFRESH_SECONDS = 24 * 60 * 60

PAYMENT_PENDING = BellCounter(
    key="payment_pending",
    operation="",
    route="",
    label=_("Unpaid invoice"),
    icon="ion:card-outline",
    severity="danger",
    title=_("Your ERPlora plan has an unpaid invoice"),
    action_label=_("Pay on erplora.com"),
    due="suspends_on",
)


def notice(hub: Hub | None, now: dt.datetime) -> dict | None:
    """The bell's row of ``hub``'s unpaid plan, in the active language; ``None`` when nothing is pending."""
    photo = hub.state if hub is not None and isinstance(hub.state, dict) else {}
    if photo.get("status") != PAST_DUE:
        return None
    deadline = _deadline(hub, photo)
    row = {"count": 1, "suspends_on": photo["suspends_on"] if deadline else None}
    return {
        **bell.notice(f"base.{PAYMENT_PENDING.key}", PAYMENT_PENDING, row),
        "route": saas_url(f"{SAAS_PANEL_PATH}/billing/invoices?business={hub.id}&status=open"),
        "body": _body(deadline, now, zone_of(hub.timezone)),
    }


def refresh_every(row: Mapping[str, Any] | None, now: dt.datetime) -> int | None:
    """Seconds until the deadline of ``row``, so the bell says it went by when it does; ``None`` with none ahead."""
    deadline = row["due"] if row else None
    if deadline is None or deadline <= now:
        return None
    seconds = math.ceil((deadline - now).total_seconds())
    return min(max(seconds, MIN_BELL_REFRESH_SECONDS), MAX_REFRESH_SECONDS)


def _deadline(hub: Hub, photo: Mapping[str, Any]) -> dt.datetime | None:
    value = photo.get("suspends_on")
    if value is None:
        return None
    try:
        deadline = dt.datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        deadline = None
    if deadline is None or deadline.tzinfo is None:
        logger.warning("base.unpaid_plan_bad_deadline hub=%s: suspends_on %r is no instant.", hub.slug, value)
        return None
    return deadline


def _body(deadline: dt.datetime | None, now: dt.datetime, zone: dt.tzinfo) -> str:
    if deadline is None:
        return gettext("Pay it on erplora.com: if it is not paid soon, the business is suspended. Nothing is deleted.")
    until = formats.date_format(deadline.astimezone(zone), "DATE_FORMAT")
    if deadline <= now:
        return gettext(
            "Pay it on erplora.com: its deadline was %(until)s and the business may be suspended at any moment. "
            "Nothing is deleted."
        ) % {"until": until}
    return gettext(
        "Pay it on erplora.com: if it is not paid by %(until)s, the business is suspended. Nothing is deleted."
    ) % {"until": until}

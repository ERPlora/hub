"""The WhatsApp inbox's clock: one seam for every «now», so the tests never read the real time.

The month of the allowance is still Madrid's: the times of the inbox are said on the business's clock by its screens
(hub#779), and this month is hub#771's.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from django.utils import timezone

BUSINESS_ZONE = ZoneInfo("Europe/Madrid")


def now() -> dt.datetime:
    """The current instant, aware, in UTC."""
    return timezone.now()


def business_month() -> str:
    """The current calendar month on the business's clock, ``YYYY-MM``."""
    return now().astimezone(BUSINESS_ZONE).strftime("%Y-%m")

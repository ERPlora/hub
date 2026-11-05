"""The WhatsApp inbox's clock: one seam for every «now», so the tests never read the real time."""

import datetime as dt

from django.utils import timezone


def now() -> dt.datetime:
    """The current instant, aware, in UTC."""
    return timezone.now()


def allowance_month() -> str:
    """The month the plan's messages are counted in, ``YYYY-MM``: erplora.com's, which counts them and refuses a send
    by a UTC month and says so in ``usage_month``. It is on no business's clock: on one of its own the Hub would call
    a month spent, or new, hours before erplora.com does (hub#771)."""
    return now().astimezone(dt.UTC).strftime("%Y-%m")

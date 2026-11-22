"""What the kitchen's reads share: the groups of statuses, how many names an ambiguous reference lists, the
settings row (or the factory values, receiving everything, while it is missing) and the business's clock.
"""

import datetime as dt

from django.utils import timezone

from apps.kitchen.models import ItemStatus, KitchenSettings, TicketStatus
from base.business import business_zone, zone_name

IN_FLIGHT = (TicketStatus.PENDING, TicketStatus.PREPARING, TicketStatus.READY)
COOKING = (TicketStatus.PENDING, TicketStatus.PREPARING)
TO_DO = (ItemStatus.PENDING, ItemStatus.PREPARING)
STRUCK = (ItemStatus.VOIDED, ItemStatus.CANCELLED)
#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5
#: A settings row lost (a database emptied): the kitchen receives everything.
EPOCH = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)

FACTORY = {
    "show_timer": True,
    "warning_minutes": 15,
    "critical_minutes": 30,
    "color_coding": True,
    "sound_enabled": True,
    "sound_volume": 70,
    "sound_tone": "chime",
    "print_pass": False,
    "works_from_screen": True,
    "default_order_type": "dine_in",
}


def business_day(moment: dt.datetime) -> dt.date:
    return timezone.localtime(moment, business_zone()).date()


def start_of(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.min, tzinfo=business_zone())


def number_of(day: dt.date, sequence: int) -> str:
    return f"{day:%Y%m%d}-{sequence:04d}"


def current_settings() -> KitchenSettings:
    """The settings row, or the factory values (receiving everything) when it is missing."""
    row = KitchenSettings.objects.first()
    return row if row is not None else KitchenSettings(**FACTORY, receiving_since=EPOCH)


def settings_out(row: KitchenSettings) -> dict:
    return {**{name: getattr(row, name) for name in FACTORY}, "timezone": zone_name()}

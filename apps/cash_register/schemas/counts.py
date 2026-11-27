"""What a count of the drawer must bring: some note or coin counted, or a total typed by hand (zero too)."""

from django.utils.translation import gettext_lazy as _

COUNT_SOMETHING = _("Count the drawer: give its notes and coins or its total.")


def counts_something(denominations, total: int | None) -> bool:
    """Whether a count's ``denominations`` (bills and coins, face value → pieces) or its ``total`` count anything."""
    if total is not None:
        return True
    if denominations is None:
        return False
    return any(pieces > 0 for kind in (denominations.bills, denominations.coins) for pieces in kind.values())

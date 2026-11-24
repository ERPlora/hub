"""The order of a write's card (``ai={"summary": …}``): the data that say what it is first, then what the card
computes, then the rest as the form asks it. A normal card's line shows only its first three data (``cardLine`` of
@erplora/ui), so a write whose form asks first for something else puts first what the person checks before saying yes:
whom a payment goes to, the cart a line goes into, the guest of a booking."""

from collections.abc import Callable, Collection, Sequence

from live.context import OperationContext

Summary = Callable[[OperationContext, dict, list[dict]], list[dict]]


def first(fields: list[dict], names: Sequence[str], *computed: dict, dropped: Collection[str] = ()) -> list[dict]:
    """The data of ``fields`` named in ``names``, in that order (those not said, skipped); then ``computed``; then the
    rest as they came. None twice: a computed datum takes the place of the one said by its name. ``dropped`` are left
    out."""
    leading = sorted((field for field in fields if field["name"] in names), key=lambda field: names.index(field["name"]))
    taken = {*names, *(datum["name"] for datum in computed), *dropped}
    return [*leading, *computed, *(field for field in fields if field["name"] not in taken)]


def said_first(*names: str) -> Summary:
    """The ``summary`` of a card that only puts ``names`` first (``first``)."""

    def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
        return first(fields, names)

    return summary

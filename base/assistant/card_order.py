"""The order of a write's card (``ai={"summary": …}``): the data that say what it is first, then what the card
computes, then the rest as the form asks it. A normal card's line shows only its first three data (``cardLine`` of
@erplora/ui), so a write whose form asks first for something else puts first what the person checks before saying yes:
whom a payment goes to, the cart a line goes into, the guest of a booking."""

from collections.abc import Callable, Collection, Sequence

from live.context import OperationContext

Summary = Callable[[OperationContext, dict, list[dict]], list[dict]]


def put_first(fields: list[dict], names: Sequence[str], *computed: dict, dropped: Collection[str] = ()) -> list[dict]:
    """The data of ``fields`` named in ``names``, in that order (those not said, skipped); then ``computed``; then the
    rest as they came. None twice: a computed datum takes the place of the one said by its name. ``dropped`` are left
    out."""
    leading = sorted((field for field in fields if field["name"] in names), key=lambda field: names.index(field["name"]))
    taken = {*names, *(datum["name"] for datum in computed), *dropped}
    return [*leading, *computed, *(field for field in fields if field["name"] not in taken)]


def said_first(*names: str) -> Summary:
    """The ``summary`` of a card that only puts ``names`` first (``put_first``)."""

    def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
        return put_first(fields, names)

    return summary


def together(fields: list[dict], name: str, names: Sequence[str]) -> dict | None:
    """The data of ``fields`` named in ``names`` as one datum ``name``, their values in that order (those not said,
    skipped; an amount with its money): what says one thing on a line that has room for three (a booking's service
    and who does it). ``None`` when none was said; one alone, as it is."""
    said = sorted(
        (field for field in fields if field["name"] in names and field["kind"] != "empty"),
        key=lambda field: names.index(field["name"]),
    )
    if not said:
        return None
    if len(said) == 1:
        return said[0]
    return {"name": name, "label": said[0]["label"], "kind": "object", "value": {field["name"]: _value(field) for field in said}}


def _value(field: dict) -> object:
    """A datum's value inside another, as the card's screen reads one there: an amount with its kind and money."""
    if field["kind"] == "money":
        return {key: field[key] for key in ("kind", "value", "money") if key in field}
    return field["value"]

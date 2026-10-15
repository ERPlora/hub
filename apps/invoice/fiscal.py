"""The fiscal arithmetic of a document, pure: it reads and writes nothing.

- The number: ``render_number`` writes a series' counter with its format (``{prefix}``, ``{code}``,
  ``{year}``, ``{seq}``, ``{seq:01d}``…``{seq:09d}``; the width is a minimum, never a cut);
  ``format_is_valid`` refuses a format without a sequence (every document would carry the same number)
  or without the year (next year's series, born from this one, would repeat its numbers);
  ``number_fits`` says whether a series' widest number is VeriFactu's ``NumSerieFactura`` (at most 60
  printable ASCII characters).
- The breakdown: one entry per **fiscal key** (tax, regime, qualification, exemption cause, rate and
  equivalence surcharge), the shape VeriFactu's ``Desglose`` reads. ``close_charged`` closes what a sale
  charged without moving a cent (VAT included: the key's base by division, its quota by difference,
  handed back to the lines by largest remainder; VAT on top: the lines' own figures);
  ``close_manual`` closes a manual invoice (VAT on top, one quota per key over the sum of the bases,
  handed back to the lines by largest remainder).
- ``audit`` refuses what does not square before anything is numbered.
- A rectification by differences: ``remaining`` (the original minus its live rectifications, key by
  key) and ``prorate`` (an amount spread over what is left of each key; taking it all copies the
  figures without rounding).

Money is whole cents with a sign; rates are ``Decimal`` and travel as text with two decimals («21.00»).
The rounding is tax's (``round_half_up``, half away from zero), the single one of the platform.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal

from apps.tax.queries import round_half_up, split_amount

DEFAULT_FORMAT = "{prefix}-{year}-{seq:06d}"
FORMAT_MAX_LENGTH = 60
NUMBER_MAX_LENGTH = 60
#: The widest sequence a number is checked with (nine digits: a billion documents a year).
WIDEST_SEQUENCE = 999_999_999
_SEQ = re.compile(r"\{seq(?::0([1-9])d)?\}")
_HUNDRED = Decimal(100)
_TWO_PLACES = Decimal("0.01")
SUBJECT = "subject"
ORDINARY_TYPES = ("F1", "F2", "F3")


# ── The number ──────────────────────────────────────────────────────────────────────────────────


def render_number(template: str, *, prefix: str, code: str, year: int, seq: int) -> str:
    """The document number: ``template`` (empty = ``DEFAULT_FORMAT``) with its placeholders filled."""

    def sequence(match: re.Match) -> str:
        width = match.group(1)
        return str(seq).zfill(int(width)) if width else str(seq)

    text = _SEQ.sub(sequence, template or DEFAULT_FORMAT)
    return (
        text.replace("{year}", str(year))
        .replace("{code}", code)
        .replace("{prefix}", prefix)
    )


def is_printable_ascii(text: str) -> bool:
    """Only the printable ASCII characters (space to «~»), the ones ``NumSerieFactura`` admits."""
    return all(" " <= char <= "~" for char in text)


def format_is_valid(template: str) -> bool:
    """One line of at most 60 printable ASCII characters with the year and a sequence placeholder."""
    return (
        0 < len(template) <= FORMAT_MAX_LENGTH
        and is_printable_ascii(template)
        and "{year}" in template
        and _SEQ.search(template) is not None
    )


def number_fits(template: str, *, prefix: str, code: str, year: int) -> bool:
    """Whether every number of a series is a ``NumSerieFactura``: its widest one (nine-digit sequence)
    has at most 60 characters, all printable ASCII."""
    widest = render_number(template, prefix=prefix, code=code, year=year, seq=WIDEST_SEQUENCE)
    return len(widest) <= NUMBER_MAX_LENGTH and is_printable_ascii(widest)


# ── Keys and entries ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FiscalKey:
    """What an operation is for the tax agency; two lines with the same key are one breakdown entry."""

    tax: str
    regime: str
    cls: str
    exempt_reason: str
    rate: Decimal
    surcharge_rate: Decimal = Decimal(0)

    @property
    def order(self) -> tuple:
        # Stable whatever the order of the lines: tax, regime, exemption, class; the higher rate first.
        return (
            self.tax,
            self.regime,
            self.exempt_reason,
            self.cls,
            -self.rate,
            -self.surcharge_rate,
        )


def _rate_text(rate: Decimal) -> str:
    return str(Decimal(rate).quantize(_TWO_PLACES))


def entry(key: FiscalKey, *, base: int, quota: int, surcharge_quota: int = 0) -> dict:
    """A breakdown entry, as ``Invoice.tax_breakdown`` keeps it."""
    return {
        "tax": key.tax,
        "regime": key.regime,
        "qualification": key.cls,
        "exempt_reason": key.exempt_reason,
        "rate": _rate_text(key.rate),
        "surcharge_rate": _rate_text(key.surcharge_rate),
        "base": base,
        "quota": quota,
        "surcharge_quota": surcharge_quota,
    }


def key_of(item: dict) -> FiscalKey:
    """The key of a breakdown entry."""
    return FiscalKey(
        tax=item["tax"],
        regime=item["regime"],
        cls=item["qualification"],
        exempt_reason=item.get("exempt_reason", ""),
        rate=Decimal(str(item["rate"])),
        surcharge_rate=Decimal(str(item.get("surcharge_rate", "0"))),
    )


def gross_of(item: dict) -> int:
    """What an entry is worth: base + quota + surcharge."""
    return item["base"] + item["quota"] + item.get("surcharge_quota", 0)


def negate(entries: Iterable[dict]) -> list[dict]:
    return [
        entry(
            key_of(item),
            base=-item["base"],
            quota=-item["quota"],
            surcharge_quota=-item.get("surcharge_quota", 0),
        )
        for item in entries
    ]


# ── Sharing cents ───────────────────────────────────────────────────────────────────────────────


def allocate(total: int, weights: Sequence[int]) -> list[int]:
    """``total`` cents shared by non-negative ``weights``: floors, then one cent each to the largest
    remainders (ties to the earlier position). Σ parts == total; all weights 0 → all to the first."""
    if not weights:
        return []
    whole = sum(weights)
    if whole <= 0:
        return [total] + [0] * (len(weights) - 1)
    sign = -1 if total < 0 else 1
    amount = abs(total)
    parts = [amount * weight // whole for weight in weights]
    remainders = [(amount * weight) % whole for weight in weights]
    left = amount - sum(parts)
    for index in sorted(range(len(weights)), key=lambda i: (-remainders[i], i))[:left]:
        parts[index] += 1
    return [sign * part for part in parts]


# ── Closing ─────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Line:
    """A line's money and its fiscal key; ``category`` names the tax category it was closed in."""

    key: FiscalKey
    base: int
    tax: int
    total: int
    category: str = ""


@dataclass
class Closed:
    """A closed document: its breakdown entries (sorted), its lines (same order as given), the audit's
    tolerance per key (cents of honest rounding) and the header's figures."""

    entries: list[dict]
    lines: list[Line]
    tolerance: dict[FiscalKey, int] = field(default_factory=dict)

    @property
    def base(self) -> int:
        return sum(item["base"] for item in self.entries)

    @property
    def tax(self) -> int:
        return sum(item["quota"] + item["surcharge_quota"] for item in self.entries)

    @property
    def total(self) -> int:
        return self.base + self.tax


def _groups(lines: Sequence[Line]) -> dict[FiscalKey, list[int]]:
    groups: dict[FiscalKey, list[int]] = {}
    for index, line in enumerate(lines):
        groups.setdefault(line.key, []).append(index)
    return groups


def _rates(key: FiscalKey) -> list[Decimal]:
    return [key.rate, key.surcharge_rate] if key.surcharge_rate else [key.rate]


def close_charged(lines: Sequence[Line], *, tax_included: bool) -> Closed:
    """The breakdown of what a sale charged: each key's money (Σ line totals) never moves."""
    out = [replace(line) for line in lines]
    entries, tolerance = [], {}
    for key, members in _groups(lines).items():
        gross = sum(lines[i].total for i in members)
        if tax_included:
            base, tax, quotas = split_amount(gross, _rates(key), tax_included=True)
            bases = allocate(base, [lines[i].total for i in members])
            for i, line_base in zip(members, bases, strict=True):
                out[i].base, out[i].tax = line_base, out[i].total - line_base
            tolerance[key] = 1
        else:
            base = sum(lines[i].base for i in members)
            tax = sum(lines[i].tax for i in members)
            main = (
                round_half_up(base * key.rate / _HUNDRED) if key.surcharge_rate else tax
            )
            quotas = [main, tax - main] if key.surcharge_rate else [tax]
            tolerance[key] = max(1, len({lines[i].category for i in members}))
        entries.append(
            entry(key, base=base, quota=quotas[0], surcharge_quota=sum(quotas[1:]))
        )
    entries.sort(key=lambda item: key_of(item).order)
    return Closed(entries=entries, lines=out, tolerance=tolerance)


def close_manual(lines: Sequence[Line]) -> Closed:
    """The breakdown of a manual invoice: each key's quota is computed once over the sum of its bases
    and handed back to its lines by largest remainder, so the printed concepts add up to the total."""
    out = [replace(line) for line in lines]
    entries, tolerance = [], {}
    for key, members in _groups(lines).items():
        base = sum(lines[i].base for i in members)
        main = round_half_up(base * key.rate / _HUNDRED)
        surcharge = (
            round_half_up(base * key.surcharge_rate / _HUNDRED)
            if key.surcharge_rate
            else 0
        )
        shares = allocate(main + surcharge, [lines[i].base for i in members])
        for i, share in zip(members, shares, strict=True):
            out[i].tax, out[i].total = share, out[i].base + share
        entries.append(entry(key, base=base, quota=main, surcharge_quota=surcharge))
        tolerance[key] = 1
    entries.sort(key=lambda item: key_of(item).order)
    return Closed(entries=entries, lines=out, tolerance=tolerance)


# ── The audit ───────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuditFailure:
    """Why a document cannot be issued: a domain code and the figures its message names."""

    code: str
    params: dict


def audit(
    entries: Sequence[dict],
    tolerance: dict[FiscalKey, int],
    *,
    base: int,
    tax: int,
    invoice_type: str,
) -> AuditFailure | None:
    """``None`` when the breakdown squares: only a subject key carries a quota, each quota crosses its
    rate within the key's tolerance, the header is the sum of the breakdown and an ordinary document
    (F1, F2, F3) never adds up below zero (0,00 € is an honest comped ticket)."""
    for item in entries:
        key = key_of(item)
        if key.cls != SUBJECT and (item["quota"] or item["surcharge_quota"]):
            return AuditFailure(
                "invoice.quota_on_non_subject_class",
                {"quota": item["quota"] + item["surcharge_quota"], "qualification": key.cls},
            )
        allowed = tolerance.get(key, 1)
        for quota, rate in (
            (item["quota"], key.rate),
            (item["surcharge_quota"], key.surcharge_rate),
        ):
            expected = round_half_up(item["base"] * rate / _HUNDRED)
            if abs(quota - expected) > allowed:
                return AuditFailure(
                    "invoice.tax_quota_mismatch",
                    {
                        "quota": quota,
                        "base": item["base"],
                        "rate": _rate_text(rate),
                        "expected": expected,
                    },
                )
    declared_base = sum(item["base"] for item in entries)
    declared_tax = sum(item["quota"] + item["surcharge_quota"] for item in entries)
    if (declared_base, declared_tax) != (base, tax):
        return AuditFailure(
            "invoice.totals_mismatch",
            {
                "base": base,
                "tax": tax,
                "declared_base": declared_base,
                "declared_tax": declared_tax,
            },
        )
    if invoice_type in ORDINARY_TYPES and base + tax < 0:
        return AuditFailure("invoice.negative_total", {"total": base + tax})
    return None


# ── Rectifying by differences ───────────────────────────────────────────────────────────────────


def remaining(
    original: Sequence[dict], rectifications: Iterable[Sequence[dict]]
) -> list[dict]:
    """What is left of each key of ``original`` after the (negative) entries of its rectifications."""
    left = {key_of(item): dict(item) for item in original}
    for entries in rectifications:
        for item in entries:
            key = key_of(item)
            if key not in left:
                continue
            kept = left[key]
            kept["base"] += item["base"]
            kept["quota"] += item["quota"]
            kept["surcharge_quota"] = kept.get("surcharge_quota", 0) + item.get(
                "surcharge_quota", 0
            )
    return [
        entry(
            key,
            base=item["base"],
            quota=item["quota"],
            surcharge_quota=item["surcharge_quota"],
        )
        for key, item in left.items()
    ]


def _within(shares: list[int], caps: Sequence[int]) -> list[int]:
    """``shares`` with none above its cap: what overflows goes to the others by the room they have left
    (largest remainder). Σ shares never moves while it fits in Σ caps."""
    over = sum(max(share - cap, 0) for share, cap in zip(shares, caps, strict=True))
    if not over:
        return shares
    kept = [min(share, cap) for share, cap in zip(shares, caps, strict=True)]
    rooms = [cap - share for share, cap in zip(kept, caps, strict=True)]
    return [share + extra for share, extra in zip(kept, allocate(over, rooms), strict=True)]


def prorate(
    left: Sequence[dict], amount: int, weights: Sequence[int] | None = None
) -> list[dict]:
    """The (negative) entries of a rectification of ``amount`` cents over what is ``left`` of each key:
    the amount shared by ``weights`` (by default each key's money; a refund of articles weighs only
    their keys) without taking more than is left of a key (largest remainder), the base by proportion
    (half up) and the quota by difference (with a surcharge, the main quota closes by its rate and the
    surcharge takes the rest). A key taken whole keeps its figures to the cent."""
    caps = [max(gross_of(item), 0) for item in left]
    weighed = weights if weights is not None and sum(weights) > 0 else caps
    shares = _within(allocate(amount, list(weighed)), caps)
    out = []
    for item, share in zip(left, shares, strict=True):
        key, gross = key_of(item), gross_of(item)
        if share == gross:
            base, quota, surcharge = (
                item["base"],
                item["quota"],
                item.get("surcharge_quota", 0),
            )
        elif gross == 0:
            base = quota = surcharge = 0
        else:
            base = round_half_up(Decimal(share) * item["base"] / gross)
            if key.surcharge_rate:
                quota = round_half_up(base * key.rate / _HUNDRED)
                surcharge = share - base - quota
            else:
                quota, surcharge = share - base, 0
        out.append(entry(key, base=-base, quota=-quota, surcharge_quota=-surcharge))
    return out

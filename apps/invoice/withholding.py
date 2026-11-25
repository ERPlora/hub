"""The IRPF withholding of a manual invoice (INVOICE-F03), pure: what the customer keeps of the base to pay it to the tax
agency for whoever bills. It takes from what is collected and from nothing else: the base, the tax and the total of the
invoice stay as they are, and VeriFactu's record has no place for it.
"""

from decimal import Decimal

from apps.tax.queries.calculation import round_half_up

#: The usual rates of the tax agency's table, the general one first.
RATES = (15, 7, 1, 19)


def withheld(base: int, rate: int | Decimal | None) -> int:
    """The cents withheld of ``base``, with its sign; none without a rate."""
    return round_half_up(Decimal(base) * rate / 100) if rate else 0


def columns(base: int, rate: int | Decimal | None) -> dict:
    """What a document of ``base`` keeps of its withholding."""
    return {"withholding_rate": rate, "withholding_amount": withheld(base, rate)}

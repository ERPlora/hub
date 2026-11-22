"""The business's currency, its decimals and its notes and coins: what a count of the drawer adds up to."""

from decimal import Decimal, InvalidOperation

from babel.numbers import get_currency_precision
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import operation

from apps.cash_register.schemas import CurrencyOut, EmptyIn
from apps.sale.queries.business import business_currency

UNKNOWN_DENOMINATION = _("%(value)s is not a note or coin of %(currency)s.")
NO_DENOMINATIONS = _(
    "There is no table of notes and coins for %(currency)s: count the drawer and give its total."
)

#: The notes and coins of the till count, per currency, largest first (face value in major units): the
#: eighteen of the product. Only what circulates today; a currency that is not
#: here has no breakdown and its count is a total.
DENOMINATIONS: dict[str, dict[str, list[str]]] = {
    "EUR": {
        "bills": ["500", "200", "100", "50", "20", "10", "5"],
        "coins": ["2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"],
    },
    "USD": {
        "bills": ["100", "50", "20", "10", "5", "2", "1"],
        "coins": ["0.50", "0.25", "0.10", "0.05", "0.01"],
    },
    "GBP": {
        "bills": ["50", "20", "10", "5"],
        "coins": ["2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"],
    },
    "CHF": {
        "bills": ["1000", "200", "100", "50", "20", "10"],
        "coins": ["5", "2", "1", "0.50", "0.20", "0.10", "0.05"],
    },
    "PLN": {
        "bills": ["500", "200", "100", "50", "20", "10"],
        "coins": ["5", "2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"],
    },
    "RON": {
        "bills": ["500", "200", "100", "50", "20", "10", "5", "1"],
        "coins": ["0.50", "0.10", "0.05", "0.01"],
    },
    "MXN": {
        "bills": ["1000", "500", "200", "100", "50", "20"],
        "coins": ["10", "5", "2", "1", "0.50"],
    },
    "JPY": {
        "bills": ["10000", "5000", "2000", "1000"],
        "coins": ["500", "100", "50", "10", "5", "1"],
    },
    "KWD": {
        "bills": ["20", "10", "5", "1", "0.5", "0.25"],
        "coins": ["0.1", "0.05", "0.02", "0.01", "0.005"],
    },
    "SEK": {
        "bills": ["1000", "500", "200", "100", "50", "20"],
        "coins": ["10", "5", "2", "1"],
    },
    "NOK": {
        "bills": ["1000", "500", "200", "100", "50"],
        "coins": ["20", "10", "5", "1"],
    },
    "DKK": {
        "bills": ["1000", "500", "200", "100", "50"],
        "coins": ["20", "10", "5", "2", "1", "0.50"],
    },
    "BRL": {
        "bills": ["200", "100", "50", "20", "10", "5", "2"],
        "coins": ["1", "0.50", "0.25", "0.10", "0.05"],
    },
    "CZK": {
        "bills": ["5000", "2000", "1000", "500", "200", "100"],
        "coins": ["50", "20", "10", "5", "2", "1"],
    },
    "HUF": {
        "bills": ["20000", "10000", "5000", "2000", "1000", "500"],
        "coins": ["200", "100", "50", "20", "10", "5"],
    },
    "COP": {
        "bills": ["100000", "50000", "20000", "10000", "5000", "2000"],
        "coins": ["1000", "500", "200", "100", "50"],
    },
    "CLP": {
        "bills": ["20000", "10000", "5000", "2000", "1000"],
        "coins": ["500", "100", "50", "10"],
    },
    "PEN": {
        "bills": ["200", "100", "50", "20", "10"],
        "coins": ["5", "2", "1", "0.50", "0.20", "0.10"],
    },
}


# The business's currency (``business_currency``) is Sales' own, imported above: the one each sale charged now keeps
# (its country's, from ``base.business.get``; on ERPlora's own hub, its issuer's country's), so the drawer always adds
# up and paints its sales in their currency.


def currency_decimals(currency: str) -> int:
    """The decimals of ``currency`` (ISO 4217) as CLDR knows them: 2 in EUR, 0 in JPY, 3 in KWD."""
    return get_currency_precision(currency)


def _face(value: str) -> Decimal | None:
    try:
        face = Decimal(str(value))
    except InvalidOperation:
        return None
    return face if face.is_finite() and face > 0 else None


def normalized_count(denominations: dict, currency: str) -> dict[str, dict[str, int]]:
    """The notes and coins counted, keyed as the currency's table writes them, without empty boxes.

    A face value that is not one of the currency's (or a currency without a table) is a 422.
    """
    table = DENOMINATIONS.get(currency)
    out: dict[str, dict[str, int]] = {}
    for kind in ("bills", "coins"):
        known = {_face(face): face for face in (table or {}).get(kind, [])}
        for face, pieces in (denominations.get(kind) or {}).items():
            key = known.get(_face(face))
            if table is None:
                raise InvalidPayload(
                    str(NO_DENOMINATIONS) % {"currency": currency},
                    fields={
                        "denominations": str(NO_DENOMINATIONS) % {"currency": currency}
                    },
                )
            if key is None:
                message = str(UNKNOWN_DENOMINATION) % {
                    "value": face,
                    "currency": currency,
                }
                raise InvalidPayload(message, fields={"denominations": message})
            if pieces:
                out.setdefault(kind, {})[key] = pieces
    return out


def count_total(denominations: dict, currency: str) -> int:
    """The total of a count in whole minor units: each face value scaled once with the currency's decimals."""
    scale = Decimal(10) ** currency_decimals(currency)
    counted = normalized_count(denominations, currency)
    return sum(
        int(Decimal(face) * scale) * pieces
        for kind in counted.values()
        for face, pieces in kind.items()
    )


@operation(
    "cash_register.currency.get",
    kind="query",
    permission="cash_register.view_session",
    input=EmptyIn,
    output=CurrencyOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what currency and decimals does the business use?",
                "list the notes and coins to count the drawer",
            ),
            "es": (
                "dime la divisa y los decimales del negocio",
                "lista los valores de billetes y monedas del negocio",
            ),
        },
        "description": "The business's currency, its decimals and its notes and coins (face values in major units, largest "
        "first), which a count by notes and coins takes."
    },
)
def get_currency(ctx: OperationContext, params: EmptyIn) -> dict:
    currency = business_currency(ctx)
    table = DENOMINATIONS.get(currency, {})
    with translation.override(ctx.language):
        return {
            "currency": currency,
            "decimals": currency_decimals(currency),
            "bills": table.get("bills", []),
            "coins": table.get("coins", []),
        }

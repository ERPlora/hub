"""The code a ticket carries for its customer to ask for its full invoice (INVOICE-F04).

``<sale number>-<signature>``: the signature is the first 60 bits, in Crockford's base32, of an HMAC-SHA256 of the
sale's id with the server's secret key. It is never stored: every sale charged as a ticket has it, the same on every
reprint, and nobody can make one without the key. Another business's sale has another id, so its code opens nothing
here even when the numbers match. Codes signed before the key changed still open while the old key stays in
``SECRET_KEY_FALLBACKS``.
"""

import datetime as dt
import hmac

from django.conf import settings
from django.utils.crypto import salted_hmac

from apps.sale.models import Sale
from apps.sale.models import Settings as SaleSettings

#: Four years from the charge: the limitation period (art. 66 LGT), the one art. 15.3 RD 1619/2012 gives a rectifying
#: invoice; no rule sets another for the full invoice a customer may demand (art. 7.2 and 7.3).
CODE_LIFETIME = dt.timedelta(days=4 * 365 + 1)
SIGNATURE_LENGTH = 12
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
#: What a person typing a code may write instead: Crockford's own readings.
_TYPED = str.maketrans({"O": "0", "I": "1", "L": "1"})
_SALT = "apps.sale.receipt_code"


def _signature(sale: Sale, secret: str) -> str:
    digest = salted_hmac(_SALT, str(sale.id), secret=secret, algorithm="sha256").digest()
    bits = int.from_bytes(digest[:8]) >> (64 - 5 * SIGNATURE_LENGTH)
    return "".join(_ALPHABET[(bits >> 5 * (SIGNATURE_LENGTH - 1 - i)) & 31] for i in range(SIGNATURE_LENGTH))


def receipt_code(sale: Sale) -> str | None:
    """The code of a sale charged as a ticket; none for one charged as an invoice."""
    if sale.document_type != SaleSettings.DocumentType.TICKET:
        return None
    return f"{sale.number}-{_signature(sale, settings.SECRET_KEY)}"


def sale_of_code(code: str) -> Sale | None:
    """The sale of this business whose ticket carries ``code`` (as typed); none when it opens nothing."""
    number, _, signature = code.strip().upper().translate(_TYPED).rpartition("-")
    if not number or len(signature) != SIGNATURE_LENGTH:
        return None
    sale = Sale.objects.filter(number=number, document_type=SaleSettings.DocumentType.TICKET).first()
    if sale is None:
        return None
    secrets = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    if not any(hmac.compare_digest(signature, _signature(sale, secret)) for secret in secrets):
        return None
    return sale


def expired(sale: Sale, now: dt.datetime) -> bool:
    """Whether the code of ``sale`` no longer opens it at ``now``."""
    return now > sale.created_at + CODE_LIFETIME

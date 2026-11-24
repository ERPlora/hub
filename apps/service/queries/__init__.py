"""Read operations of the service app (``READ ONLY``): the catalog, its categories, the settings, who
performs each service, the vouchers of the catalog, the ones sold with their balance, their movements
and the checks that say whether a voucher can be voided, adjusted or spent, and why not.

Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break, so pages never overlap. The
``find_*`` helpers resolve how a person names a record (assistant, voice): by id, else an exact name,
else the only name that contains it; several → 409 ``*_ambiguous`` naming them. The balance of a
voucher sold is computed here, from its sessions and its adjustments (WORKBOOK «Para quien lo
mantiene»); services.py reads it again after locking the voucher's row.
"""

from . import (
    assignments as assignments,
    catalog as catalog,
    categories as categories,
    grant_checks as grant_checks,
    grants as grants,
    movements as movements,
    packages as packages,
    reads as reads,
    records as records,
    recovery as recovery,
    sale_numbers as sale_numbers,
    settings as settings,
    tender as tender,
)

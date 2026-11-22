"""Whose a sale is (SALE-F28 to SALE-F31): whoever charged it, and the person whose staff record it was attributed to.
Without «See all sales» a person reads and touches only theirs. A voucher session done outside the till is the
professional's who did it."""

from django.db.models import Q

from apps.sale.models import Sale, VoucherSession
from base.queries.ownership import Owned

SALES = Owned(
    Sale,
    all_permission="sale.view_all_sales",
    mine=lambda person: Q(created_by=person.username) | Q(staff_id__in=person.records),
)

VOUCHER_SESSIONS = Owned(
    VoucherSession,
    all_permission="sale.view_all_sales",
    mine=lambda person: Q(staff_id__in=person.records),
)

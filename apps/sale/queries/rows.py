"""Rows a write names, held until its transaction ends."""

from django.db.models import QuerySet


def held(rows: QuerySet) -> list:
    """``rows``, each held until this transaction ends with a key-share lock taken in the same read, for a write
    that names them (an open-price line at a department, a tender of a payment method). The Hub admin's «Delete»
    locks them first (``services.orders.lock_rows``): it waits for this write and then finds what it wrote, so it answers
    «Cannot delete» instead of either of them failing at its COMMIT. A key share is the lock the foreign key itself
    takes at the COMMIT, taken earlier: it only stops a deletion, while another write that names the row (every sale
    names Cash) or changes it (a rename, a deactivation) goes on. One being deleted meanwhile is read once the
    deletion ends: gone, as one deleted before. The ORM has no ``FOR KEY SHARE``: it is appended to the SQL the ORM
    wrote, and the rows still come from the hub's database by the router."""
    sql, params = rows.query.sql_with_params()
    return list(rows.model.objects.raw(f"{sql} FOR KEY SHARE", params))

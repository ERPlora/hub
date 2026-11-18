"""What every read of VeriFactu shares: the permission that sees it, and the page a list answers."""

from django.db.models import QuerySet

VIEW = "verifactu.view_record"


def page(queryset: QuerySet, limit: int, offset: int, convert) -> dict:
    return {
        "rows": [convert(item) for item in queryset[offset : offset + limit]],
        "total": queryset.count(),
        "limit": limit,
        "offset": offset,
    }

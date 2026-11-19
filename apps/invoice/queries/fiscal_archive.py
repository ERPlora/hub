"""What Invoicing reads for a business that left, as its config answers the platform (``fiscal_documents_kept`` and
``fiscal_archive_documents``): whether its database holds invoices, and every one of them for the fiscal archive."""

from collections.abc import Iterator

from apps.invoice.models import Invoice

#: How many invoices are read at once.
PAGE_ROWS = 500


def keeps_fiscal_documents() -> bool:
    """Whether this database holds its invoices (``fiscal_documents_kept`` on this app's config), of any status: a draft
    counts too, for what it asks is whether a database can go, and that cannot be undone."""
    return Invoice.objects.exists()


def invoices() -> Iterator[Invoice]:
    """Every invoice of the active hub's database, whatever its status, a page at a time by its key (UUIDv7: in the
    order they were issued)."""
    last = None
    while True:
        page = Invoice._base_manager.order_by("pk")
        if last is not None:
            page = page.filter(pk__gt=last)
        found = list(page[:PAGE_ROWS])
        if not found:
            return
        yield from found
        last = found[-1].pk

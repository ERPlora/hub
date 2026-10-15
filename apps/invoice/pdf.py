"""The PDF of a document: WeasyPrint prints the A4 HTML ``queries.render_document`` writes (the platform hub's PDF
of ERPlora's invoices, PLAN-SAAS §4), offline and outside any transaction.

Nothing outside the page is fetched: the document is whole (its styles inline, VeriFactu's QR a ``data:`` URI), so
the fetcher allows ``data:`` alone and a URL among the texts it prints never makes the server call anywhere (it is
left out with a warning). WeasyPrint needs Pango and HarfBuzz (the image installs them, Dockerfile); it is imported
when a PDF is asked for, so a machine without them still runs everything else. On a Mac, Homebrew's library
directories are offered to the loader (its ``ctypes.util.find_library`` reads them at that moment).
"""

import os
import sys

HOMEBREW_LIBRARIES = ("/opt/homebrew/lib", "/usr/local/lib")


def _weasyprint():
    if sys.platform == "darwin" and not os.environ.get("DYLD_FALLBACK_LIBRARY_PATH"):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(HOMEBREW_LIBRARIES)
    import weasyprint
    import weasyprint.urls

    return weasyprint


def page_fetcher():
    """WeasyPrint's fetcher for a document: ``data:`` URIs only, without redirects."""
    return _weasyprint().urls.URLFetcher(
        timeout=5, allowed_protocols=("data",), allow_redirects=False
    )


def render_pdf(html: str) -> bytes:
    """``html`` (a whole page) as PDF bytes."""
    weasyprint = _weasyprint()
    return weasyprint.HTML(string=html, url_fetcher=page_fetcher()).write_pdf()

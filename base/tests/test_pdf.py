"""A whole HTML page printed as PDF with WeasyPrint, offline (``base.pdf``).

Nothing outside the page is ever fetched: a page carries its styles inline and its images as ``data:`` URIs, and a URL
among the texts it prints must never make the server call anywhere.
"""

import pytest

from base import pdf


def test_a_page_becomes_a_pdf():
    printed = pdf.render_pdf("<html><body><p>x</p></body></html>")

    assert printed.startswith(b"%PDF-")


def test_a_data_uri_is_read_from_the_page_itself():
    image = (
        "data:image/svg+xml;base64,"
        "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEiLz4="
    )

    response = pdf.page_fetcher()(image)

    assert (response.content_type, b"<svg" in response.read()) == ("image/svg+xml", True)


@pytest.mark.parametrize(
    "url",
    ["http://169.254.169.254/latest/meta-data", "https://example.com/logo.png", "file:///etc/passwd"],
)
def test_nothing_outside_the_page_is_fetched(url):
    with pytest.raises(ValueError, match="disallowed protocol"):
        pdf.page_fetcher()(url)


def test_a_page_naming_an_outside_url_still_prints_without_it():
    printed = pdf.render_pdf(
        '<html><body><img src="http://169.254.169.254/x.png"><p>x</p></body></html>'
    )

    assert printed.startswith(b"%PDF-")

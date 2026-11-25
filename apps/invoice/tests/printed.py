"""What a PDF of an invoice says when it is opened, for the tests that print one: its words, its QR, its language, its
title, its pages and its fonts, read by a PDF library and a QR reader that know nothing of how it was made."""

import base64
import ctypes
from collections import Counter
from html.parser import HTMLParser

import pypdfium2
import pypdfium2.raw as pdfium
import zxingcpp

#: A4 in points, as a page of the file measures it.
A4 = (595, 842)


class _Shown(HTMLParser):
    """The text nodes of a page's body."""

    def __init__(self):
        super().__init__()
        self.texts: list[str] = []

    def handle_data(self, data):
        self.texts.append(data)


def words(text: str) -> Counter[str]:
    """The words of ``text``, however the paper spaces, breaks or capitalises them."""
    return Counter(text.casefold().split())


def words_of_page(html: str) -> Counter[str]:
    """The words the A4 page ``html`` shows."""
    page = _Shown()
    page.feed(html.partition("<body>")[2])
    return words(" ".join(page.texts))


def content(out) -> bytes:
    return base64.b64decode(out.content_base64)


def opened(out) -> pypdfium2.PdfDocument:
    return pypdfium2.PdfDocument(content(out))


def text(out) -> str:
    return "\n".join(page.get_textpage().get_text_bounded() for page in opened(out))


def sizes(out) -> list[tuple[int, int]]:
    """Each page's width and height, in points."""
    return [tuple(round(side) for side in page.get_size()) for page in opened(out)]


def title(out) -> str:
    return opened(out).get_metadata_dict()["Title"]


def language(out) -> str:
    document = opened(out)
    size = pdfium.FPDFCatalog_GetLanguage(document.raw, None, 0)
    buffer = (pdfium.FPDF_WCHAR * (size // ctypes.sizeof(pdfium.FPDF_WCHAR)))()
    pdfium.FPDFCatalog_GetLanguage(document.raw, buffer, size)
    return bytes(buffer).decode("utf-16-le").rstrip("\0")


def qr_urls(out) -> list[str]:
    """What a phone reads pointing at each QR of the file."""
    return [
        code.text for page in opened(out) for code in zxingcpp.read_barcodes(page.render(scale=3).to_pil())
    ]


def fonts_not_embedded(out) -> int:
    """How many of its texts are written in a font the file does not carry with it."""
    missing = 0
    for page in opened(out):
        for shown in page.get_objects(filter=[pdfium.FPDF_PAGEOBJ_TEXT]):
            font = pdfium.FPDFTextObj_GetFont(shown.raw)
            missing += pdfium.FPDFFont_GetIsEmbedded(font) != 1
    return missing

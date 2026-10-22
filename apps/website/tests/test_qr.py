"""The website's QR: the hub's public address, in PNG to print and SVG to scale."""

import io
import re

import qrcode
import qrcode.constants
from django.test import RequestFactory
from PIL import Image

from apps.website.qr import BORDER, BOX_SIZE, public_url, qr_image

URL = "https://pepe.erplora.com/"
OTHER = "https://other.erplora.com/"


def expected_dark(url: str) -> set[tuple[int, int]]:
    """The dark modules ``(x, y)`` of ``url``'s QR, quiet zone included, as qrcode lays it out."""
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=BORDER)
    code.add_data(url)
    code.make(fit=True)
    return {(x, y) for y, row in enumerate(code.get_matrix()) for x, dark in enumerate(row) if dark}


def png_dark(png: bytes) -> set[tuple[int, int]]:
    """The dark modules read back from a PNG's pixels (the centre of each box)."""
    image = Image.open(io.BytesIO(png)).convert("L")
    count = image.size[0] // BOX_SIZE
    centre = BOX_SIZE // 2
    return {
        (x, y)
        for y in range(count)
        for x in range(count)
        if image.getpixel((x * BOX_SIZE + centre, y * BOX_SIZE + centre)) < 128
    }


def svg_dark(svg: bytes) -> set[tuple[int, int]]:
    """The dark modules of an SVG path, one ``M<x>,<y>H…`` square per module."""
    return {(int(x), int(y)) for x, y in re.findall(rb"M(\d+),(\d+)H", svg)}


def test_qr_encodes_the_hub_public_url_in_png_and_svg():
    png = qr_image(URL, "png")
    assert png.startswith(b"\x89PNG")
    assert png_dark(png) == expected_dark(URL)
    assert png_dark(png) != expected_dark(OTHER)
    svg = qr_image(URL, "svg")
    assert svg.startswith(b"<svg")
    assert svg_dark(svg) == expected_dark(URL)
    assert svg_dark(qr_image(OTHER, "svg")) == expected_dark(OTHER)


def test_the_public_url_is_the_hubs_own_address_as_the_browser_reaches_it(settings):
    settings.ALLOWED_HOSTS = [".localhost", ".erplora.com"]
    local = RequestFactory().get("/api/website/qr", HTTP_HOST="a.localhost:8000")
    assert public_url("a", local) == "http://a.localhost:8000/"
    behind_the_alb = RequestFactory().get("/api/website/qr", HTTP_HOST="pepe.erplora.com", HTTP_X_FORWARDED_PROTO="https")
    assert public_url("pepe", behind_the_alb) == "https://pepe.erplora.com/"


def test_without_a_request_the_public_url_is_https_on_the_base_domain(settings):
    settings.HUB_BASE_DOMAIN = "erplora.com"
    assert public_url("pepe") == "https://pepe.erplora.com/"

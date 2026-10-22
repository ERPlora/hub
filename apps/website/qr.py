"""The QR code of a hub's website: its public address, in PNG (to print) or SVG (to scale).

Drawn with ``qrcode`` (the library VeriFactu's QR already uses, ``apps/verifactu/chain.py``), medium error correction,
the standard quiet zone of four modules.
"""

import io

import qrcode
import qrcode.constants
import qrcode.image.pil
import qrcode.image.svg
from django.conf import settings

#: Quiet zone around the code, in modules (the standard's four).
BORDER = 4
#: Pixels per module in the PNG: 10 gives a ~330 px image for a short address, sharp when printed at 3 cm.
BOX_SIZE = 10
CONTENT_TYPES = {"png": "image/png", "svg": "image/svg+xml"}


def public_url(slug: str, request=None) -> str:
    """The hub's public address: as the browser reached it (scheme, host and port), or ``https://<slug>.<domain>/``."""
    if request is not None:
        return request.build_absolute_uri("/")
    return f"https://{slug}.{settings.HUB_BASE_DOMAIN}/"


def qr_image(url: str, image_format: str) -> bytes:
    """The QR of ``url`` as a PNG or an SVG document."""
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=BORDER, box_size=BOX_SIZE)
    code.add_data(url)
    code.make(fit=True)
    if image_format == "svg":
        return code.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string()
    buffer = io.BytesIO()
    code.make_image(image_factory=qrcode.image.pil.PilImage).save(buffer, format="PNG")
    return buffer.getvalue()

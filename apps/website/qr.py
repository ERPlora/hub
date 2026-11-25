"""The QR of a hub's website: its public address, or that address right at its catalog, the section's own anchor (to
print for the tables: it opens on the business's own domain too), as the file the editor downloads. The code itself is
drawn by ``base.qr``."""

import base64

from base.qr import public_url, qr_image

CONTENT_TYPES = {"png": "image/png", "svg": "image/svg+xml"}
#: What each QR opens, after the address, and the name its file starts with.
TARGETS = {"page": ("", "website-qr"), "catalog": ("#catalog", "website-catalog-qr")}


def qr_file(slug: str, request, image_format: str, target: str) -> dict:
    """The QR of ``target`` (``page`` or ``catalog``) of ``slug``'s website as the file the editor downloads."""
    anchor, name = TARGETS[target]
    url = public_url(slug, request) + anchor
    return {
        "format": image_format,
        "url": url,
        "content_type": CONTENT_TYPES[image_format],
        "filename": f"{name}-{slug}.{image_format}",
        "content_base64": base64.b64encode(qr_image(url, image_format)).decode("ascii"),
    }

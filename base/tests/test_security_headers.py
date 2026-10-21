"""The security headers of the Hub's HTML: the SPA on a hub host and the staff's admin on the platform host.

Both keep the windows they open (Cross-Origin-Opener-Policy ``same-origin-allow-popups``): Meta's window to connect
a WhatsApp number (WHATSAPP_INBOX-F01/F02) answers its opener. The other headers stay as they were.
"""

import re

import pytest
from django.utils.csp import build_policy

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]
HOST = "a.localhost:8000"
PLATFORM = "hubs.localhost:8000"


def security_headers(response, settings) -> dict[str, str]:
    # The page carries the configured CSP; what that policy holds is pinned by config/tests/test_settings.py.
    [nonce] = re.findall(r"'nonce-([^']+)'", response["Content-Security-Policy"])
    assert response["Content-Security-Policy"] == build_policy(settings.SECURE_CSP, nonce)
    return {
        name: response.headers.get(name)
        for name in ("Cross-Origin-Opener-Policy", "Referrer-Policy", "X-Content-Type-Options", "X-Frame-Options")
    }


EXPECTED = {
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def test_the_spa_on_a_hub_host_keeps_the_windows_it_opens(client, settings):
    response = client.get("/demo/items", HTTP_HOST=HOST)
    assert response.status_code == 200
    assert security_headers(response, settings) == EXPECTED


def test_the_admin_on_the_platform_host_keeps_the_windows_it_opens_too(client, settings, superuser):
    # One policy for the whole Hub: the staff's admin opens no window of another origin, and allow-popups still
    # cuts a page of another origin that opens it.
    client.force_login(superuser)
    response = client.get("/admin/", HTTP_HOST=PLATFORM)
    assert response.status_code == 200
    assert security_headers(response, settings) == EXPECTED

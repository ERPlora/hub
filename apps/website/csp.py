"""The Content Security Policy of a hub's public website and of the editor's preview (round 2026-10-21).

The SPA runs on a nonce with ``'strict-dynamic'`` and Trusted Types (``live.csp.base_policy``). The public page
cannot: its HTML is cached and shared between visitors (``public_home``), so it carries no nonce, and it loads one
bundle of our own, ``frontend/website.ts`` (Bootstrap and the catalog's refresh), under ``script-src 'self'``. It
has no inline script and no HTML of the owner's. The preview is the same page, framed by the editor on the hub's own
host. Applied per response with ``response._csp_config``; with DEBUG, Vite's dev server serves the bundle (as
``saas/public/csp.py`` does for the SaaS's public web).
"""

from django.conf import settings
from django.utils.csp import CSP

#: Directives the dev server widens with DEBUG (``script-src`` too: without a nonce its modules need their source).
_DEV_SERVER_DIRECTIVES = ("script-src", "style-src", "img-src", "font-src", "connect-src")


def public_policy() -> dict[str, list[str]]:
    """The public page's policy, a fresh dict on every call, read from the settings of the moment."""
    policy = {
        "default-src": [CSP.SELF],
        "script-src": [CSP.SELF],
        "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
        "img-src": [CSP.SELF, "data:"],
        "font-src": [CSP.SELF, "data:"],
        "connect-src": [CSP.SELF],
        "frame-ancestors": [CSP.NONE],
        "base-uri": [CSP.SELF],
        "form-action": [CSP.SELF],
        "object-src": [CSP.NONE],
        "report-uri": ["/csp-report/"],
    }
    dev_server = settings.LIVE["spa"].get("dev_server")
    if settings.DEBUG and dev_server:
        for directive in _DEV_SERVER_DIRECTIVES:
            policy[directive].append(dev_server)
        policy["connect-src"].append("ws" + dev_server.removeprefix("http"))
    return policy


def preview_policy() -> dict[str, list[str]]:
    """The preview's policy: the public one, framed only by the hub's own pages (the editor)."""
    return {**public_policy(), "frame-ancestors": [CSP.SELF]}

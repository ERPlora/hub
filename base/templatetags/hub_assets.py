"""``{% hub_assets "<entry>" %}``: the ``<link>`` and ``<script>`` tags of an entry of the Hub's Vite build.

The SPA's own HTML comes from ``live.spa.render_spa``; a page of the Hub that is not the SPA links another entry of
the same build (``build.rollupOptions.input`` in ``vite.config.ts``), such as a hub's public website,
``{% hub_assets "frontend/website.ts" %}``. The files come from ``live.spa.spa_assets``: the build's manifest under
``/static/spa/``, or, with DEBUG, the dev server's HMR client and the entry (which then injects its own CSS).

A page rendered with the response's CSP nonce in its context (``csp_nonce``, the ``csp`` context processor of a
``RequestContext``) puts it on every script and modulepreload, as ``'strict-dynamic'`` requires. A page rendered
without one (the public website, ``script-src 'self'``, whose HTML is cached and must not replay a nonce) gets tags
without it.
"""

from __future__ import annotations

from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from live.spa import spa_assets

register = template.Library()


@register.simple_tag(takes_context=True)
def hub_assets(context, entry: str) -> SafeString:
    """The stylesheets, modulepreloads and module scripts of ``entry`` (a key of the Vite manifest)."""
    assets = spa_assets(context.get("request"), entry=entry)
    nonce = context.get("csp_nonce")
    nonce_attr = format_html(' nonce="{}"', nonce) if nonce else ""
    lines = [
        *(format_html('<link rel="stylesheet" href="{}">', href) for href in assets["css"]),
        *(format_html('<link rel="modulepreload" href="{}"{}>', href, nonce_attr) for href in assets["preload"]),
        *(format_html('<script type="module" src="{}"{}></script>', src, nonce_attr) for src in assets["scripts"]),
    ]
    return format_html_join("\n", "{}", ((line,) for line in lines))

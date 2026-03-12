"""
Configuration Views

Only PWA (Progressive Web App) views.
All other views have been migrated to:
- Dashboard: apps.main.index.views
- Settings: apps.main.settings.views
- Modules: apps.system.modules.views
"""
import json
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings

from .models import StoreConfig
from .services.pwa_icons import get_icon_urls, get_favicon_url

# Default ERPlora icons (fallback when no custom logo)
_DEFAULT_ICONS = [
    {"src": "/static/img/icons/icon-72x72.png", "sizes": "72x72", "type": "image/png"},
    {"src": "/static/img/icons/icon-96x96.png", "sizes": "96x96", "type": "image/png"},
    {"src": "/static/img/icons/icon-128x128.png", "sizes": "128x128", "type": "image/png"},
    {"src": "/static/img/icons/icon-144x144.png", "sizes": "144x144", "type": "image/png"},
    {"src": "/static/img/icons/icon-152x152.png", "sizes": "152x152", "type": "image/png"},
    {"src": "/static/img/icons/icon-192x192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/img/icons/icon-384x384.png", "sizes": "384x384", "type": "image/png"},
    {"src": "/static/img/icons/icon-512x512.png", "sizes": "512x512", "type": "image/png"},
]


# ============================================================================
# PWA (Progressive Web App) Views
# ============================================================================

@require_http_methods(["GET"])
def pwa_manifest(request):
    """
    Serve dynamic PWA manifest.json based on StoreConfig.
    Uses customer's business name and logo if configured,
    falls back to ERPlora branding otherwise.
    """
    store = StoreConfig.get_solo()
    name = store.business_name or 'ERPlora Hub'
    short_name = (store.business_name or 'ERPlora')[:12]

    # Use custom icons if the customer uploaded a logo
    custom_icons = get_icon_urls() if store.logo else None
    icons = custom_icons or _DEFAULT_ICONS

    manifest = {
        "name": name,
        "short_name": short_name,
        "description": f"{name} - Point of Sale",
        "theme_color": "#ffffff",
        "background_color": "#ffffff",
        "display": "standalone",
        "scope": "/",
        "orientation": "any",
        "start_url": "/",
        "dir": "ltr",
        "lang": getattr(request, 'LANGUAGE_CODE', 'en'),
        "icons": icons,
    }
    return JsonResponse(manifest)


@require_http_methods(["GET"])
def pwa_serviceworker(request):
    """
    Serve PWA service worker JavaScript file.
    """
    sw_path = Path(django_settings.BASE_DIR) / 'static' / 'js' / 'serviceworker.js'

    if sw_path.exists():
        return FileResponse(
            open(sw_path, 'rb'),
            content_type='application/javascript'
        )

    # Fallback: return minimal service worker
    return JsonResponse(
        {"error": "Service worker not found"},
        status=404
    )


def pwa_offline(request):
    """
    Serve offline fallback page for PWA.
    """
    return render(request, 'offline.html')


@require_http_methods(["GET"])
def pwa_favicon(request):
    """
    Serve dynamic favicon — custom if logo is set, otherwise redirect to static default.
    """
    from django.shortcuts import redirect as http_redirect

    custom_url = get_favicon_url(size=32)
    if custom_url:
        return http_redirect(custom_url)

    # Fallback to default ERPlora favicon
    return http_redirect('/static/img/favicon.ico')

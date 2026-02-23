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
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings


# ============================================================================
# PWA (Progressive Web App) Views
# ============================================================================

@require_http_methods(["GET"])
def pwa_manifest(request):
    """
    Serve PWA manifest.json with app configuration.
    """
    manifest = {
        "name": "ERPlora Hub",
        "short_name": "ERPlora",
        "description": "ERPlora Hub - Point of Sale System",
        "theme_color": "#ffffff",
        "background_color": "#ffffff",
        "display": "standalone",
        "scope": "/",
        "orientation": "any",
        "start_url": "/",
        "dir": "ltr",
        "lang": "en-US",
        "icons": [
            {"src": "/static/img/icons/icon-72x72.png", "sizes": "72x72", "type": "image/png"},
            {"src": "/static/img/icons/icon-96x96.png", "sizes": "96x96", "type": "image/png"},
            {"src": "/static/img/icons/icon-128x128.png", "sizes": "128x128", "type": "image/png"},
            {"src": "/static/img/icons/icon-144x144.png", "sizes": "144x144", "type": "image/png"},
            {"src": "/static/img/icons/icon-152x152.png", "sizes": "152x152", "type": "image/png"},
            {"src": "/static/img/icons/icon-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/img/icons/icon-384x384.png", "sizes": "384x384", "type": "image/png"},
            {"src": "/static/img/icons/icon-512x512.png", "sizes": "512x512", "type": "image/png"},
        ]
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

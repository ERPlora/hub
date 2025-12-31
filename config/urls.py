"""
URL Configuration for ERPlora Hub

URL Structure
=============

/api/v1/                    REST API (JSON responses)
├── /auth/                  Authentication (login, logout, PIN)
├── /employees/             Employee management (DRF ViewSet)
├── /config/                Hub configuration
├── /modules/               Module management
├── /system/                System utilities (updates, notifications)
└── /sync/                  Cloud sync & backups

/                           Web UI (HTML + HTMX)
├── /                       Root redirect (→ /home/ or /login/)
├── /login/, /logout/       Authentication pages
├── /setup/                 First-time setup wizard
├── /home/                  Home dashboard
├── /files/                 File browser
├── /settings/              Settings page
├── /employees/             Employee management
├── /modules/               My Modules (installed)
├── /marketplace/           Marketplace (modules, hubs, etc.)
└── /m/<module_id>/         Dynamic module routes (active modules)

/htmx/                      HTMX Partials (HTML fragments)
├── /sidebar/               Sidebar refresh
├── /connection-status/     Connection indicator
├── /update-notification/   Update badge
└── /health/                Health check

Namespaces
==========
API:  api_auth, api_employees, api_config, api_modules, api_system, api_sync
UI:   auth, main, store, setup, configuration, htmx
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from apps.modules_runtime.router import module_urlpatterns
from apps.core.views import set_language
from apps.configuration.views import pwa_manifest, pwa_serviceworker, pwa_offline

# Import API URL patterns from each app
from apps.auth.login.api import api_urlpatterns as auth_api_urls
from apps.accounts.api import api_urlpatterns as employees_api_urls
from apps.configuration.api import api_urlpatterns as config_api_urls
from apps.system.modules.api import api_urlpatterns as modules_api_urls
from apps.core.api import api_urlpatterns as system_api_urls
from apps.sync.urls import api_urlpatterns as sync_api_urls

urlpatterns = [
    path('admin/', admin.site.urls),

    # ==========================================================================
    # REST API v1 - All JSON endpoints consolidated here
    # ==========================================================================
    path('api/v1/auth/', include((auth_api_urls, 'api_auth'))),
    path('api/v1/employees/', include((employees_api_urls, 'api_employees'))),
    path('api/v1/config/', include((config_api_urls, 'api_config'))),
    path('api/v1/modules/', include((modules_api_urls, 'api_modules'))),
    path('api/v1/system/', include((system_api_urls, 'api_system'))),
    path('api/v1/sync/', include((sync_api_urls, 'api_sync'))),

    # API Documentation (Swagger/OpenAPI)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # ==========================================================================
    # Health check endpoint (for Cloud monitoring)
    # ==========================================================================
    path('ht/', include('health_check.urls')),

    # ==========================================================================
    # PWA (Progressive Web App)
    # ==========================================================================
    path('manifest.json', pwa_manifest, name='pwa_manifest'),
    path('serviceworker.js', pwa_serviceworker, name='pwa_serviceworker'),
    path('offline/', pwa_offline, name='pwa_offline'),

    # Language switcher (auto-detected from browser)
    path('set-language/', set_language, name='set_language'),

    # ==========================================================================
    # Web UI Routes - Clean URLs without /dashboard/ prefix
    # ==========================================================================

    # Auth routes (login, logout, etc.)
    path('', include('apps.auth.login.urls')),

    # Setup wizard (initial configuration)
    path('setup/', include('apps.main.setup.urls')),

    # Main UI routes (flat structure for clear active states)
    path('', include('apps.main.urls')),  # Home at /

    # Module store (installed modules management)
    path('modules/', include('apps.system.modules.urls')),

    # Marketplace (multi-store: modules, hubs, components, products)
    path('marketplace/', include('apps.marketplace.urls')),

    # ==========================================================================
    # HTMX Partials - UI fragments for dynamic updates
    # ==========================================================================
    # Note: These return HTML fragments, not JSON
    path('htmx/', include('apps.core.urls')),

    # Configuration (maintenance utilities) - internal use
    path('config/', include('apps.configuration.urls')),
]


# Añadir las URLs dinámicas de modules
urlpatterns += module_urlpatterns

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Django Debug Toolbar (only if installed and in INSTALLED_APPS)
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns

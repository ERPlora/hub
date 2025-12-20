"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
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

urlpatterns = [
    path('admin/', admin.site.urls),

    # ==========================================================================
    # REST API v1
    # ==========================================================================
    path('api/v1/auth/', include((auth_api_urls, 'api_auth'))),
    path('api/v1/employees/', include((employees_api_urls, 'api_employees'))),
    path('api/v1/config/', include((config_api_urls, 'api_config'))),
    path('api/v1/modules/', include((modules_api_urls, 'api_modules'))),
    path('api/v1/system/', include((system_api_urls, 'api_system'))),

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
    # Web UI Routes
    # ==========================================================================

    # Root redirect to dashboard (or login if not authenticated)
    path('', lambda request: redirect('main:index') if 'local_user_id' in request.session else redirect('auth:login'), name='root'),

    # Auth routes (login, logout, etc.)
    path('', include('apps.auth.login.urls')),

    # Setup wizard (initial configuration)
    path('setup/', include('apps.main.setup.urls')),

    # Main routes (dashboard, settings, employees)
    path('dashboard/', include('apps.main.urls')),

    # System routes (modules, marketplace)
    path('modules/', include('apps.system.modules.urls')),

    # Configuration (maintenance utilities)
    path('config/', include('apps.configuration.urls')),

    # Core utilities (health check, update notifications)
    path('', include('apps.core.urls')),

    # Sync with Cloud
    path('sync/', include('apps.sync.urls')),
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

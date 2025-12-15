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

from apps.plugins_runtime.router import plugin_urlpatterns
from apps.core.views import set_language, pwa_manifest, pwa_serviceworker, pwa_offline

urlpatterns = [
    path('admin/', admin.site.urls),

    # Health check endpoint (for Cloud monitoring)
    path('ht/', include('health_check.urls')),

    # PWA (Progressive Web App)
    path('manifest.json', pwa_manifest, name='pwa_manifest'),
    path('serviceworker.js', pwa_serviceworker, name='pwa_serviceworker'),
    path('offline/', pwa_offline, name='pwa_offline'),

    # Language switcher (auto-detected from browser)
    path('set-language/', set_language, name='set_language'),

    # Root redirect to dashboard
    path('', lambda request: redirect('main:index'), name='root'),

    # NEW: Auth routes (login, logout, etc.)
    path('', include('apps.auth.login.urls')),

    # NEW: Main routes (dashboard, settings, employees) - all under 'main' namespace
    path('dashboard/', include('apps.main.urls')),

    # NEW: System routes (plugins, marketplace)
    path('plugins/', include('apps.system.plugins.urls')),

    # LEGACY: Keep old URLs and namespaces working during transition
    # Configuration namespace (dashboard, settings, plugins)
    path('', include('apps.configuration.urls')),
    # Health check and core utilities
    path('', include('apps.core.urls')),
    # Sync with Cloud
    path('', include('apps.sync.urls')),
    # Employee API and accounts namespace (login, logout, employees)
    path('', include('apps.accounts.urls')),
]


# Añadir las URLs dinámicas de plugins
urlpatterns += plugin_urlpatterns

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

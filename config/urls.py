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

from apps.plugins_runtime.router import plugin_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    # Health check endpoint (for Cloud monitoring)
    path('ht/', include('health_check.urls')),
    # Refactored app URLs
    path('', include('apps.core.urls')),  # Health check, core views
    path('', include('apps.configuration.urls')),  # Root redirect, Dashboard, POS, settings (must be first for root URL)
    path('', include('apps.accounts.urls')),  # Login, employees, auth
    path('', include('apps.sync.urls')),  # Sync, updates, FRP
]


# Añadir las URLs dinámicas de plugins
urlpatterns += plugin_urlpatterns

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

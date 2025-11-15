"""
URLs del plugin Example Plugin.

Define las rutas del plugin. Todas las URLs están bajo el prefijo /example/

Ejemplos:
    /example/ → vista principal (index)
    /example/api/status/ → API de estado

Naming:
    - Vistas HTML: nombre descriptivo (index, list, detail, create)
    - APIs: prefijo 'api_' (api_status, api_create, api_delete)
"""

from django.urls import path
from . import views

app_name = 'example'

urlpatterns = [
    # Vista principal
    path('', views.index, name='index'),

    # API endpoints
    path('api/status/', views.api_status, name='api_status'),
]

"""
Main app URLs

Combines all main business area routes under the 'main' namespace.
"""
from django.urls import path, include

from apps.main.index import views as index_views
from apps.main.settings import views as settings_views
from apps.main.files import views as files_views

app_name = 'main'

urlpatterns = [
    # Dashboard home
    path('', index_views.index, name='index'),

    # Files (local file browser & database download)
    path('files/', files_views.index, name='files'),

    # Settings
    path('settings/', settings_views.index, name='settings'),

    # Employees (includes index + API endpoints)
    path('employees/', include('apps.main.employees.urls')),
]

"""
Main app URLs

Flat URL structure for clear navigation states:
/               Home (dashboard)
/files/         File browser
/settings/      Settings
/employees/     Employee management
/roles/         Roles and permissions management
"""
from django.urls import path, include

from apps.main.index import views as index_views
from apps.main.settings import views as settings_views
from apps.main.files import views as files_views

app_name = 'main'

urlpatterns = [
    # Home (dashboard) at root
    path('', index_views.index, name='index'),

    # Files (local file browser & database download)
    path('files/', files_views.index, name='files'),

    # Settings
    path('settings/', settings_views.index, name='settings'),

    # Employees (includes index + API endpoints)
    path('employees/', include('apps.main.employees.urls')),

    # Roles and permissions
    path('roles/', include('apps.main.roles.urls')),
]

"""
Main app URLs

Combines all main business area routes under the 'main' namespace.
"""
from django.urls import path, include

from apps.main.index import views as index_views
from apps.main.settings import views as settings_views
from apps.main.employees import views as employees_views

app_name = 'main'

urlpatterns = [
    # Dashboard home
    path('', index_views.index, name='index'),

    # Settings
    path('settings/', settings_views.index, name='settings'),

    # Employees
    path('employees/', employees_views.index, name='employees'),
]

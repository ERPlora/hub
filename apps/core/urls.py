"""
Core URLs - HTMX Partials

System-level HTML fragments for dynamic UI updates.
Mounted at /htmx/ in config/urls.py

These return HTML fragments, not JSON.
API endpoints are in apps/core/api.py (mounted at /api/v1/system/)
"""
from django.urls import path
from . import views

app_name = 'htmx'

urlpatterns = [
    # Sidebar refresh (for module changes)
    path('sidebar/', views.sidebar_partial, name='sidebar'),

    # Connection status (WiFi indicator)
    path('connection-status/', views.connection_status, name='connection_status'),

    # Update notification badge
    path('update-notification/', views.update_notification, name='update_notification'),
    path('update-notification/dismiss/', views.update_notification_dismiss, name='update_notification_dismiss'),

    # Health check (for internal use and Docker healthcheck)
    path('health/', views.health_check, name='health_check'),
]

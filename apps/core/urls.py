"""
Core URLs

System-level endpoints only:
- Health check (for Docker/monitoring)
- Update notification partial (HTMX)

Note: Update API endpoints are now in api/v1/system/ (see apps/core/api.py)
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Health check endpoint (for Docker healthcheck)
    path('health/', views.health_check, name='health_check'),

    # Connection status (HTMX partial - WiFi indicator)
    path('connection-status/', views.connection_status, name='connection_status'),

    # Update notification (HTMX partial)
    path('update-notification/', views.update_notification, name='update_notification'),
]

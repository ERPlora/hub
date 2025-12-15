"""
Configuration URLs

Only contains:
- Database maintenance utilities

All other routes are now in their proper apps:
- Dashboard: apps.main.index
- Settings: apps.main.settings
- Plugins: apps.system.plugins
"""
from django.urls import path
from . import views_maintenance

app_name = 'configuration'

urlpatterns = [
    # Database Maintenance (admin utilities)
    path('maintenance/scan-orphaned/', views_maintenance.scan_orphaned_data, name='scan_orphaned_data'),
    path('maintenance/clean-orphaned/', views_maintenance.clean_orphaned_data, name='clean_orphaned_data'),
]

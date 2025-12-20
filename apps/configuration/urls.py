"""
Configuration URLs

Contains:
- Database maintenance utilities
- Local file browser and downloads

All other routes are now in their proper apps:
- Dashboard: apps.main.index
- Settings: apps.main.settings
- Modules: apps.system.modules
"""
from django.urls import path
from . import views_maintenance, views_files

app_name = 'configuration'

urlpatterns = [
    # Database Maintenance (admin utilities)
    path('maintenance/scan-orphaned/', views_maintenance.scan_orphaned_data, name='scan_orphaned_data'),
    path('maintenance/clean-orphaned/', views_maintenance.clean_orphaned_data, name='clean_orphaned_data'),

    # Local Files Browser
    path('files/browse/', views_files.file_browser, name='file_browser'),
    path('files/download/', views_files.download_file, name='download_file'),
    path('files/download-database/', views_files.download_database, name='download_database'),
    path('files/storage-info/', views_files.get_storage_info, name='storage_info'),
]

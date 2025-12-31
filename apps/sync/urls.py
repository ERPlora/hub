"""
Sync URLs - Cloud synchronization and updates

All endpoints are REST API (JSON responses).
Mounted at /api/v1/sync/ in config/urls.py
"""
from django.urls import path
from . import views_update, views_backup

# API endpoints for /api/v1/sync/
api_urlpatterns = [
    # Backup
    path('backup/database/', views_backup.backup_database, name='backup_database'),

    # Updates
    path('update/check/', views_update.check_updates, name='update_check'),
    path('update/status/', views_update.update_status, name='update_status'),
    path('update/download/', views_update.download_update, name='update_download'),
    path('update/install/', views_update.install_update, name='update_install'),
    path('update/apply/', views_update.apply_update, name='update_apply'),
    path('update/rollback/', views_update.rollback_update, name='update_rollback'),
    path('update/notification/', views_update.update_notification, name='update_notification'),
]

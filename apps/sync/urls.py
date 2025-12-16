from django.urls import path
from . import views_update, views_backup

app_name = 'sync'

urlpatterns = [
    # Backup API endpoints
    path('api/backup/database/', views_backup.backup_database, name='backup_database'),

    # Update API endpoints
    path('api/update/check/', views_update.check_updates, name='update_check'),
    path('api/update/status/', views_update.update_status, name='update_status'),
    path('api/update/download/', views_update.download_update, name='update_download'),
    path('api/update/install/', views_update.install_update, name='update_install'),
    path('api/update/apply/', views_update.apply_update, name='update_apply'),
    path('api/update/rollback/', views_update.rollback_update, name='update_rollback'),
    path('api/update/notification/', views_update.update_notification, name='update_notification'),
]

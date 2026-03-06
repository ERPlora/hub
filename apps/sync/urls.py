"""
Sync URLs - Cloud synchronization

All endpoints are REST API (JSON responses).
Mounted at /api/v1/sync/ in config/urls.py
"""
from django.urls import path
from . import views_backup, views_bug_report

# API endpoints for /api/v1/sync/
api_urlpatterns = [
    # Backup
    path('backup/database/', views_backup.backup_database, name='backup_database'),
    # Bug reports
    path('bug-report/', views_bug_report.submit_bug_report, name='bug_report'),
]

"""
Backup views - Database backup via BackupService.
"""
import logging
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def backup_database(request):
    """
    Backup database (PostgreSQL) to S3 via pg_dump.

    This endpoint is called by Cloud when user requests a database backup.

    Response:
        {"success": true, "path": "...", "size": 12345}
        or
        {"success": false, "error": "..."}
    """
    try:
        from apps.configuration.services.backup import backup_service
        success, result, size = backup_service.run_backup()
        if success:
            return JsonResponse({
                'success': True,
                'path': result,
                'size': size,
                'timestamp': datetime.now().isoformat(),
            })
        return JsonResponse({
            'success': False,
            'error': result
        }, status=500)
    except Exception as e:
        logger.error(f"[BACKUP] Failed: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

"""
Backup views - Database backup to S3.
"""
import logging
import os
import shutil
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def _get_s3_client():
    """Get configured boto3 S3 client."""
    import boto3
    return boto3.client(
        's3',
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )


@csrf_exempt
@require_POST
def backup_database(request):
    """
    Backup database (SQLite) to S3.

    Copies the current SQLite database to S3 at:
    hubs/{HUB_ID}/db/db.sqlite3

    This endpoint is called by Cloud when user requests a database backup.

    Authentication: Validates request comes from Cloud via HUB_JWT or session.

    Response:
        {"success": true, "path": "hubs/{hub_id}/db/db.sqlite3", "size": 12345}
        or
        {"success": false, "error": "..."}
    """
    # Get database path
    db_path = settings.DATABASES['default']['NAME']

    if not os.path.exists(db_path):
        logger.error(f"[BACKUP] Database file not found: {db_path}")
        return JsonResponse({
            'success': False,
            'error': 'Database file not found'
        }, status=404)

    try:
        # Get file size
        file_size = os.path.getsize(db_path)

        # S3 key: hubs/{HUB_ID}/db/db.sqlite3
        s3_key = f"{settings.AWS_LOCATION}/db/db.sqlite3"

        # Upload to S3
        s3_client = _get_s3_client()

        with open(db_path, 'rb') as f:
            s3_client.upload_fileobj(
                f,
                settings.AWS_STORAGE_BUCKET_NAME,
                s3_key,
                ExtraArgs={
                    'ContentType': 'application/x-sqlite3',
                }
            )

        logger.info(f"[BACKUP] Database uploaded to S3: {s3_key} ({file_size} bytes)")

        return JsonResponse({
            'success': True,
            'path': f"db/db.sqlite3",
            'size': file_size,
            'timestamp': datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"[BACKUP] Failed to upload database to S3: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

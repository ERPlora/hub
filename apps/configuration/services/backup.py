"""
Backup Service - Automated database backups with S3/local storage support.

This service handles:
- Database backups (SQLite copy or PostgreSQL pg_dump)
- Storage to S3 (web/cloud) or local filesystem (desktop)
- Retention policies (days and max count)
- Scheduling via APScheduler
"""

import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class BackupService:
    """
    Handles database backups with support for both S3 and local storage.

    Storage mode is determined automatically:
    - Web/Docker: Uses S3 (AWS_* settings must be configured)
    - Desktop: Uses local filesystem (backups_dir from DataPaths)
    """

    BACKUP_JOB_ID = 'hub_database_backup'

    def __init__(self):
        self._scheduler = None
        self._is_s3_mode = self._detect_storage_mode()

    def _detect_storage_mode(self) -> bool:
        """
        Detect if we should use S3 or local storage.

        Returns:
            bool: True if S3 mode, False if local mode
        """
        # Check for S3 credentials
        has_s3 = all([
            getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None),
            getattr(settings, 'AWS_S3_ENDPOINT_URL', None),
        ])

        # Web deployment always uses S3 if configured
        deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'local')
        if deployment_mode == 'web' and has_s3:
            return True

        return False

    def _get_s3_client(self):
        """Get configured boto3 S3 client."""
        import boto3
        return boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-central'),
        )

    def _get_local_backups_dir(self) -> Path:
        """Get local backups directory."""
        return Path(settings.BACKUPS_DIR)

    def _get_database_path(self) -> Optional[Path]:
        """
        Get path to SQLite database file.

        Returns:
            Path to SQLite database, or None if using PostgreSQL
        """
        db_config = settings.DATABASES.get('default', {})

        # Check if PostgreSQL
        engine = db_config.get('ENGINE', '')
        if 'postgresql' in engine:
            return None

        # SQLite - return the database file path
        db_name = db_config.get('NAME')
        if db_name:
            return Path(db_name)

        return None

    def _is_postgresql(self) -> bool:
        """Check if using PostgreSQL database."""
        engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
        return 'postgresql' in engine

    def _generate_backup_filename(self) -> str:
        """Generate timestamped backup filename."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        hub_id = getattr(settings, 'HUB_ID', 'local')

        if self._is_postgresql():
            return f"backup_{hub_id}_{timestamp}.sql.gz"
        else:
            return f"backup_{hub_id}_{timestamp}.sqlite3"

    def run_backup(self) -> Tuple[bool, str, int]:
        """
        Execute a database backup.

        Returns:
            Tuple of (success: bool, path: str, size: int)
        """
        from apps.configuration.models import BackupConfig

        backup_config = BackupConfig.get_solo()
        filename = self._generate_backup_filename()

        try:
            if self._is_postgresql():
                success, path, size = self._backup_postgresql(filename)
            else:
                success, path, size = self._backup_sqlite(filename)

            if success:
                # Update backup config with success info
                backup_config.last_backup_at = timezone.now()
                backup_config.last_backup_size = size
                backup_config.last_backup_path = path
                backup_config.last_error = ''
                backup_config.save()

                # Apply retention policy
                self._apply_retention_policy(backup_config)

                logger.info(f"[BACKUP] Success: {path} ({size} bytes)")
            else:
                backup_config.last_error = path  # path contains error message
                backup_config.save()
                logger.error(f"[BACKUP] Failed: {path}")

            return success, path, size

        except Exception as e:
            error_msg = str(e)
            backup_config.last_error = error_msg
            backup_config.save()
            logger.exception(f"[BACKUP] Exception during backup: {e}")
            return False, error_msg, 0

    def _backup_sqlite(self, filename: str) -> Tuple[bool, str, int]:
        """
        Backup SQLite database.

        Returns:
            Tuple of (success, path_or_error, size)
        """
        db_path = self._get_database_path()
        if not db_path or not db_path.exists():
            return False, "Database file not found", 0

        if self._is_s3_mode:
            return self._backup_sqlite_to_s3(db_path, filename)
        else:
            return self._backup_sqlite_to_local(db_path, filename)

    def _backup_sqlite_to_local(self, db_path: Path, filename: str) -> Tuple[bool, str, int]:
        """Backup SQLite to local filesystem."""
        backups_dir = self._get_local_backups_dir()
        backup_path = backups_dir / filename

        try:
            # Copy database file
            shutil.copy2(db_path, backup_path)
            size = backup_path.stat().st_size
            return True, str(backup_path), size
        except Exception as e:
            return False, f"Failed to copy database: {e}", 0

    def _backup_sqlite_to_s3(self, db_path: Path, filename: str) -> Tuple[bool, str, int]:
        """Backup SQLite to S3."""
        try:
            s3_client = self._get_s3_client()
            bucket = settings.AWS_STORAGE_BUCKET_NAME
            aws_location = getattr(settings, 'AWS_LOCATION', 'hubs/unknown')
            s3_key = f"{aws_location}/backups/{filename}"

            # Get file size
            size = db_path.stat().st_size

            # Upload to S3
            with open(db_path, 'rb') as f:
                s3_client.upload_fileobj(
                    f,
                    bucket,
                    s3_key,
                    ExtraArgs={'ContentType': 'application/x-sqlite3'}
                )

            return True, s3_key, size
        except Exception as e:
            return False, f"Failed to upload to S3: {e}", 0

    def _backup_postgresql(self, filename: str) -> Tuple[bool, str, int]:
        """
        Backup PostgreSQL database using pg_dump.

        Returns:
            Tuple of (success, path_or_error, size)
        """
        db_config = settings.DATABASES.get('default', {})

        # Build pg_dump command
        env = os.environ.copy()
        env['PGPASSWORD'] = db_config.get('PASSWORD', '')

        cmd = [
            'pg_dump',
            '-h', db_config.get('HOST', 'localhost'),
            '-p', str(db_config.get('PORT', 5432)),
            '-U', db_config.get('USER', 'postgres'),
            '-d', db_config.get('NAME', 'erplora'),
            '-Fc',  # Custom format (compressed)
        ]

        if self._is_s3_mode:
            return self._backup_postgresql_to_s3(cmd, env, filename)
        else:
            return self._backup_postgresql_to_local(cmd, env, filename)

    def _backup_postgresql_to_local(self, cmd: list, env: dict, filename: str) -> Tuple[bool, str, int]:
        """Backup PostgreSQL to local filesystem."""
        backups_dir = self._get_local_backups_dir()
        backup_path = backups_dir / filename

        try:
            with open(backup_path, 'wb') as f:
                result = subprocess.run(
                    cmd,
                    env=env,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    timeout=3600  # 1 hour timeout
                )

            if result.returncode != 0:
                error = result.stderr.decode('utf-8', errors='replace')
                return False, f"pg_dump failed: {error}", 0

            size = backup_path.stat().st_size
            return True, str(backup_path), size

        except subprocess.TimeoutExpired:
            return False, "Backup timed out after 1 hour", 0
        except Exception as e:
            return False, f"pg_dump error: {e}", 0

    def _backup_postgresql_to_s3(self, cmd: list, env: dict, filename: str) -> Tuple[bool, str, int]:
        """Backup PostgreSQL to S3."""
        import tempfile

        try:
            # Create temp file for the dump
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dump') as tmp:
                tmp_path = Path(tmp.name)

            # Run pg_dump to temp file
            with open(tmp_path, 'wb') as f:
                result = subprocess.run(
                    cmd,
                    env=env,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    timeout=3600
                )

            if result.returncode != 0:
                error = result.stderr.decode('utf-8', errors='replace')
                tmp_path.unlink(missing_ok=True)
                return False, f"pg_dump failed: {error}", 0

            # Upload to S3
            s3_client = self._get_s3_client()
            bucket = settings.AWS_STORAGE_BUCKET_NAME
            aws_location = getattr(settings, 'AWS_LOCATION', 'hubs/unknown')
            s3_key = f"{aws_location}/backups/{filename}"

            size = tmp_path.stat().st_size

            with open(tmp_path, 'rb') as f:
                s3_client.upload_fileobj(
                    f,
                    bucket,
                    s3_key,
                    ExtraArgs={'ContentType': 'application/octet-stream'}
                )

            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

            return True, s3_key, size

        except subprocess.TimeoutExpired:
            tmp_path.unlink(missing_ok=True)
            return False, "Backup timed out after 1 hour", 0
        except Exception as e:
            if 'tmp_path' in locals():
                tmp_path.unlink(missing_ok=True)
            return False, f"pg_dump error: {e}", 0

    def _apply_retention_policy(self, backup_config) -> None:
        """Apply retention policy to old backups."""
        try:
            if self._is_s3_mode:
                self._apply_retention_s3(backup_config)
            else:
                self._apply_retention_local(backup_config)
        except Exception as e:
            logger.warning(f"[BACKUP] Failed to apply retention policy: {e}")

    def _apply_retention_local(self, backup_config) -> None:
        """Apply retention policy to local backups."""
        backups_dir = self._get_local_backups_dir()
        if not backups_dir.exists():
            return

        # List all backup files
        backups = sorted(
            [f for f in backups_dir.iterdir() if f.name.startswith('backup_')],
            key=lambda f: f.stat().st_mtime,
            reverse=True  # Newest first
        )

        now = datetime.now()
        deleted_count = 0

        for i, backup_file in enumerate(backups):
            should_delete = False

            # Check max_backups limit
            if backup_config.max_backups > 0 and i >= backup_config.max_backups:
                should_delete = True

            # Check retention_days
            if backup_config.retention_days > 0:
                file_age = now - datetime.fromtimestamp(backup_file.stat().st_mtime)
                if file_age.days > backup_config.retention_days:
                    should_delete = True

            if should_delete:
                try:
                    backup_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"[BACKUP] Failed to delete old backup {backup_file}: {e}")

        if deleted_count > 0:
            logger.info(f"[BACKUP] Retention policy: deleted {deleted_count} old backups")

    def _apply_retention_s3(self, backup_config) -> None:
        """Apply retention policy to S3 backups."""
        try:
            s3_client = self._get_s3_client()
            bucket = settings.AWS_STORAGE_BUCKET_NAME
            aws_location = getattr(settings, 'AWS_LOCATION', 'hubs/unknown')
            prefix = f"{aws_location}/backups/"

            # List all backup objects
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            objects = response.get('Contents', [])

            if not objects:
                return

            # Sort by last modified (newest first)
            objects.sort(key=lambda x: x['LastModified'], reverse=True)

            now = timezone.now()
            to_delete = []

            for i, obj in enumerate(objects):
                should_delete = False

                # Check max_backups limit
                if backup_config.max_backups > 0 and i >= backup_config.max_backups:
                    should_delete = True

                # Check retention_days
                if backup_config.retention_days > 0:
                    obj_age = now - obj['LastModified']
                    if obj_age.days > backup_config.retention_days:
                        should_delete = True

                if should_delete:
                    to_delete.append({'Key': obj['Key']})

            # Delete old backups
            if to_delete:
                s3_client.delete_objects(
                    Bucket=bucket,
                    Delete={'Objects': to_delete}
                )
                logger.info(f"[BACKUP] Retention policy: deleted {len(to_delete)} old S3 backups")

        except Exception as e:
            logger.warning(f"[BACKUP] Failed to apply S3 retention policy: {e}")

    def list_backups(self) -> List[dict]:
        """
        List all available backups.

        Returns:
            List of backup info dicts with keys: name, size, created_at, path
        """
        if self._is_s3_mode:
            return self._list_backups_s3()
        else:
            return self._list_backups_local()

    def _list_backups_local(self) -> List[dict]:
        """List local backups."""
        backups_dir = self._get_local_backups_dir()
        if not backups_dir.exists():
            return []

        backups = []
        for f in backups_dir.iterdir():
            if f.name.startswith('backup_'):
                stat = f.stat()
                backups.append({
                    'name': f.name,
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_mtime),
                    'path': str(f),
                })

        return sorted(backups, key=lambda x: x['created_at'], reverse=True)

    def _list_backups_s3(self) -> List[dict]:
        """List S3 backups."""
        try:
            s3_client = self._get_s3_client()
            bucket = settings.AWS_STORAGE_BUCKET_NAME
            aws_location = getattr(settings, 'AWS_LOCATION', 'hubs/unknown')
            prefix = f"{aws_location}/backups/"

            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            objects = response.get('Contents', [])

            backups = []
            for obj in objects:
                name = obj['Key'].split('/')[-1]
                if name.startswith('backup_'):
                    backups.append({
                        'name': name,
                        'size': obj['Size'],
                        'created_at': obj['LastModified'],
                        'path': obj['Key'],
                    })

            return sorted(backups, key=lambda x: x['created_at'], reverse=True)

        except Exception as e:
            logger.error(f"[BACKUP] Failed to list S3 backups: {e}")
            return []

    # =========================================================================
    # Scheduler Integration
    # =========================================================================

    def setup_scheduler(self, scheduler) -> None:
        """
        Configure the backup job in APScheduler.

        Args:
            scheduler: APScheduler BackgroundScheduler instance
        """
        from apps.configuration.models import BackupConfig

        self._scheduler = scheduler
        backup_config = BackupConfig.get_solo()

        # Remove existing job if any
        try:
            scheduler.remove_job(self.BACKUP_JOB_ID)
        except Exception:
            pass

        if not backup_config.enabled or backup_config.frequency == 'disabled':
            logger.info("[BACKUP] Automatic backups disabled")
            return

        # Add new job with configured schedule
        from apscheduler.triggers.cron import CronTrigger

        trigger_kwargs = backup_config.get_cron_trigger_kwargs()
        trigger = CronTrigger(**trigger_kwargs)

        scheduler.add_job(
            self.run_backup,
            trigger=trigger,
            id=self.BACKUP_JOB_ID,
            name='Database Backup',
            replace_existing=True,
            misfire_grace_time=3600,  # Allow 1 hour grace period
        )

        logger.info(
            f"[BACKUP] Scheduled: {backup_config.frequency} at "
            f"{backup_config.time_hour:02d}:{backup_config.time_minute:02d}"
        )

    def reschedule(self) -> None:
        """
        Reschedule the backup job after config change.

        Call this after updating BackupConfig.
        """
        if self._scheduler:
            self.setup_scheduler(self._scheduler)


# Global instance
backup_service = BackupService()

"""
APScheduler Integration for Hub.

This module provides a background scheduler for automated tasks like backups.
The scheduler starts automatically when Django boots up (in apps.py ready()).

Usage:
    # Check if scheduler is running
    from apps.configuration.scheduler import scheduler
    if scheduler.running:
        print("Scheduler is running")

    # Manually trigger a backup
    from apps.configuration.services import backup_service
    backup_service.run_backup()

    # Reschedule after config change
    backup_service.reschedule()
"""

import logging
import atexit
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional['BackgroundScheduler'] = None
_initialized = False


def init_scheduler() -> bool:
    """
    Initialize and start the APScheduler.

    This should only be called once during Django startup.
    It's safe to call multiple times - subsequent calls are no-ops.

    Returns:
        bool: True if scheduler was initialized, False if already running
    """
    global scheduler, _initialized

    if _initialized:
        return False

    # Only run scheduler in web deployment mode
    # Desktop apps might handle this differently
    deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'local')

    # Skip in certain conditions
    if _should_skip_scheduler():
        logger.debug("[SCHEDULER] Skipping scheduler initialization")
        _initialized = True
        return False

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.executors.pool import ThreadPoolExecutor

        # Create scheduler with a single-thread executor
        # (backups should not run in parallel)
        executors = {
            'default': ThreadPoolExecutor(max_workers=1),
        }

        job_defaults = {
            'coalesce': True,  # Combine missed runs into one
            'max_instances': 1,  # Only one instance of each job at a time
        }

        scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC',
        )

        # Start scheduler first
        scheduler.start()

        logger.info("[SCHEDULER] Started APScheduler for Hub background tasks")

        # Setup backup job after scheduler is running
        # This may access the database, which is fine after Django is fully loaded
        try:
            from apps.configuration.services import backup_service
            backup_service.setup_scheduler(scheduler)
        except Exception as e:
            logger.warning(f"[SCHEDULER] Could not setup backup job (will retry on first access): {e}")

        # Register shutdown handler
        atexit.register(shutdown_scheduler)

        _initialized = True
        return True

    except Exception as e:
        logger.error(f"[SCHEDULER] Failed to initialize: {e}")
        _initialized = True  # Prevent retry loops
        return False


def shutdown_scheduler() -> None:
    """Gracefully shutdown the scheduler."""
    global scheduler

    if scheduler and scheduler.running:
        logger.info("[SCHEDULER] Shutting down...")
        scheduler.shutdown(wait=False)


def _should_skip_scheduler() -> bool:
    """
    Check if scheduler should be skipped.

    Returns:
        bool: True if scheduler should not run
    """
    import sys

    # Skip during migrations
    if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
        return True

    # Skip during collectstatic
    if 'collectstatic' in sys.argv:
        return True

    # Skip during tests (unless explicitly enabled)
    if 'test' in sys.argv or 'pytest' in sys.argv:
        return True

    # Skip in shell commands
    if 'shell' in sys.argv or 'shell_plus' in sys.argv:
        return True

    # Skip for management commands that don't need it
    skip_commands = [
        'check', 'showmigrations', 'dbshell', 'inspectdb',
        'clearsessions', 'flush', 'dumpdata', 'loaddata',
    ]
    for cmd in skip_commands:
        if cmd in sys.argv:
            return True

    return False


def get_scheduler_status() -> dict:
    """
    Get current scheduler status.

    Returns:
        dict with keys: running, jobs, next_run
    """
    global scheduler

    if not scheduler:
        return {
            'running': False,
            'jobs': [],
            'next_run': None,
        }

    jobs_info = []
    next_run = None

    for job in scheduler.get_jobs():
        job_info = {
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time,
        }
        jobs_info.append(job_info)

        # Track earliest next run
        if job.next_run_time:
            if next_run is None or job.next_run_time < next_run:
                next_run = job.next_run_time

    return {
        'running': scheduler.running,
        'jobs': jobs_info,
        'next_run': next_run,
    }

"""
Main System Views

System page with resource monitoring, storage info, and file browser.
"""
import os

from django.urls import reverse
from django.db import connection
from django.conf import settings

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.configuration.views_files import format_file_size

def _get_db_limit():
    """Get database size limit from plan env var (default 2 GB)."""
    max_db_gb = float(os.environ.get('MAX_DATABASE_GB', '2'))
    return int(max_db_gb * 1024 * 1024 * 1024)


def _get_database_size():
    """Get PostgreSQL database size in bytes."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        return cursor.fetchone()[0]


def _get_resource_metrics():
    """
    Get container resource metrics from cgroups v2.

    Returns dict with memory/cpu info or None if not in a container.
    """
    metrics = {}

    # Memory
    try:
        with open('/sys/fs/cgroup/memory.current', 'r') as f:
            memory_used = int(f.read().strip())
        with open('/sys/fs/cgroup/memory.max', 'r') as f:
            val = f.read().strip()
            memory_limit = int(val) if val != 'max' else 0
        metrics['memory_used_mb'] = round(memory_used / (1024 * 1024))
        metrics['memory_limit_mb'] = round(memory_limit / (1024 * 1024)) if memory_limit else 0
        if metrics['memory_limit_mb'] > 0:
            metrics['memory_percent'] = min(100, int(metrics['memory_used_mb'] / metrics['memory_limit_mb'] * 100))
        else:
            metrics['memory_percent'] = 0
    except (FileNotFoundError, ValueError, PermissionError):
        return None

    # CPU limit from env var
    cpu_limit = os.environ.get('CPU_LIMIT', '')
    if cpu_limit:
        try:
            metrics['cpu_limit'] = float(cpu_limit)
        except ValueError:
            metrics['cpu_limit'] = 0
    else:
        metrics['cpu_limit'] = 0

    # CPU usage from cgroup
    try:
        with open('/sys/fs/cgroup/cpu.stat', 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2 and parts[0] == 'usage_usec':
                    metrics['cpu_usage_usec'] = int(parts[1])
                    break
    except (FileNotFoundError, ValueError, PermissionError):
        metrics['cpu_usage_usec'] = 0

    return metrics


@login_required
@htmx_view('main/files/pages/index.html', 'main/files/partials/content.html')
def index(request):
    """System page - resources, storage, and file browser."""
    db_size = _get_database_size()
    db_limit = _get_db_limit()

    # Database size indicator
    db_percent = min(100, int((db_size / db_limit) * 100)) if db_limit else 0
    # Color thresholds at 50% and 85% of limit
    if db_percent < 50:
        db_color = 'success'
    elif db_percent < 85:
        db_color = 'warning'
    else:
        db_color = 'error'

    # Plan name from env (set by Cloud deployment)
    plan_name = os.environ.get('PLAN_NAME', '')

    # Resource metrics (only available inside Docker containers)
    resource_metrics = _get_resource_metrics()

    return {
        'current_section': 'files',
        'page_title': 'System',
        'base_path': str(settings.DATA_DIR),
        'download_url': reverse('configuration:download_database'),
        'db_size': format_file_size(db_size),
        'db_limit': format_file_size(db_limit),
        'db_percent': db_percent,
        'db_color': db_color,
        'plan_name': plan_name,
        'metrics': resource_metrics,
    }

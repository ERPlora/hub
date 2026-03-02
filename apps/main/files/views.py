"""
Main System Views

System page with storage info, resource usage and file browser.
"""
import os

from django.urls import reverse
from django.db import connection
from django.conf import settings

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.configuration.views_files import format_file_size


def _get_database_size():
    """Get PostgreSQL database size in bytes."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        return cursor.fetchone()[0]


def _get_resource_metrics():
    """Get container resource metrics from cgroups v2 (Docker) or env vars."""
    metrics = {
        'memory_used_mb': 0,
        'memory_limit_mb': 0,
        'memory_percent': 0,
        'cpu_limit': 0,
        'cpu_used': 0,
        'cpu_percent': 0,
        'is_cloud': bool(os.environ.get('HUB_ID')),
    }

    # Memory used: cgroup v2
    try:
        with open('/sys/fs/cgroup/memory.current', 'r') as f:
            memory_used = int(f.read().strip())
        metrics['memory_used_mb'] = round(memory_used / (1024 * 1024))
    except (FileNotFoundError, ValueError):
        pass

    # Memory limit: env var (Dokploy), cgroup, or Docker inspect
    mem_limit_env = os.environ.get('MEMORY_LIMIT', '')
    if mem_limit_env.endswith('m'):
        metrics['memory_limit_mb'] = int(mem_limit_env[:-1])
    elif mem_limit_env.endswith('g'):
        metrics['memory_limit_mb'] = int(mem_limit_env[:-1]) * 1024
    else:
        try:
            with open('/sys/fs/cgroup/memory.max', 'r') as f:
                val = f.read().strip()
                if val != 'max':
                    metrics['memory_limit_mb'] = round(int(val) / (1024 * 1024))
        except (FileNotFoundError, ValueError):
            pass

    if metrics['memory_limit_mb'] > 0 and metrics['memory_used_mb'] > 0:
        metrics['memory_percent'] = round(
            metrics['memory_used_mb'] / metrics['memory_limit_mb'] * 100
        )

    # CPU limit: env var (Dokploy) or cgroup
    cpu_limit_env = os.environ.get('CPU_LIMIT', '')
    if cpu_limit_env:
        try:
            metrics['cpu_limit'] = float(cpu_limit_env)
        except ValueError:
            pass
    else:
        try:
            with open('/sys/fs/cgroup/cpu.max', 'r') as f:
                parts = f.read().strip().split()
                if parts[0] != 'max':
                    metrics['cpu_limit'] = round(int(parts[0]) / int(parts[1]), 2)
        except (FileNotFoundError, ValueError, IndexError):
            pass

    # CPU usage: cgroup v2 usage_usec / uptime = average CPU cores used
    try:
        with open('/sys/fs/cgroup/cpu.stat', 'r') as f:
            for line in f:
                if line.startswith('usage_usec'):
                    cpu_usage_usec = int(line.split()[1])
                    break
            else:
                cpu_usage_usec = 0

        with open('/proc/uptime', 'r') as f:
            uptime_sec = float(f.read().split()[0])

        if uptime_sec > 0 and cpu_usage_usec > 0:
            cpu_used = cpu_usage_usec / (uptime_sec * 1_000_000)
            metrics['cpu_used'] = round(cpu_used, 2)

            if metrics['cpu_limit'] > 0:
                metrics['cpu_percent'] = min(100, round(
                    cpu_used / metrics['cpu_limit'] * 100
                ))
    except (FileNotFoundError, ValueError, IndexError):
        pass

    return metrics


@login_required
@htmx_view('main/files/pages/index.html', 'main/files/partials/content.html')
def index(request):
    """System page - storage, resources and file browser."""
    db_size = _get_database_size()
    metrics = _get_resource_metrics()

    return {
        'current_section': 'files',
        'page_title': 'System',
        'base_path': str(settings.DATA_DIR),
        'download_url': reverse('configuration:download_database'),
        'db_size': format_file_size(db_size),
        'metrics': metrics,
    }

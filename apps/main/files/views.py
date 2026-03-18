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
    """Get resource metrics from Cloud API (CloudWatch) for cloud hubs."""
    is_cloud = bool(os.environ.get('HUB_ID'))
    metrics = {
        'memory_used_mb': 0,
        'memory_limit_mb': 0,
        'memory_percent': 0,
        'cpu_limit': 0,
        'cpu_used': 0,
        'cpu_percent': 0,
        'is_cloud': is_cloud,
    }

    if not is_cloud:
        return metrics

    # Fetch from Cloud API (CloudWatch metrics)
    try:
        from apps.sync.services.cloud_api import get_cloud_api
        cloud_api = get_cloud_api()
        if cloud_api.is_configured:
            data = cloud_api.get_metrics()
            if data:
                cpu_percent = data.get('cpu_percent')
                memory_percent = data.get('memory_percent')
                memory_used_mb = data.get('memory_used_mb')
                memory_limit_mb = data.get('memory_limit_mb')
                cpu_limit = data.get('cpu_limit')

                if memory_limit_mb:
                    metrics['memory_limit_mb'] = memory_limit_mb
                if memory_used_mb:
                    metrics['memory_used_mb'] = memory_used_mb
                if memory_percent:
                    metrics['memory_percent'] = round(memory_percent)
                if cpu_limit:
                    metrics['cpu_limit'] = cpu_limit
                if cpu_percent is not None and cpu_limit:
                    metrics['cpu_used'] = round(cpu_percent * cpu_limit / 100, 2)
                    metrics['cpu_percent'] = round(cpu_percent)
    except Exception:
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

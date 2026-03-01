"""
Main System Views

System page with storage info and file browser.
"""
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


@login_required
@htmx_view('main/files/pages/index.html', 'main/files/partials/content.html')
def index(request):
    """System page - storage and file browser."""
    db_size = _get_database_size()

    return {
        'current_section': 'files',
        'page_title': 'System',
        'base_path': str(settings.DATA_DIR),
        'download_url': reverse('configuration:download_database'),
        'db_size': format_file_size(db_size),
    }

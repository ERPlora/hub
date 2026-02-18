"""
Main Files Views

Local file browser and database download page.
"""
from django.urls import reverse

from pathlib import Path

from django.conf import settings

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.configuration.views_files import format_file_size

# Database size limit: 2 GB
DB_LIMIT = 2 * 1024 * 1024 * 1024


@login_required
@htmx_view('main/files/pages/index.html', 'main/files/partials/content.html')
def index(request):
    """Files management page - browse local files and download database."""
    db_path = Path(settings.DATABASES['default']['NAME'])

    # Database size indicator
    db_size = db_path.stat().st_size if db_path.exists() else 0
    db_percent = min(100, int((db_size / DB_LIMIT) * 100)) if DB_LIMIT else 0
    if db_size < 1 * 1024 * 1024 * 1024:
        db_color = 'success'
    elif db_size < 1.7 * 1024 * 1024 * 1024:
        db_color = 'warning'
    else:
        db_color = 'error'

    return {
        'current_section': 'files',
        'page_title': 'Files',
        'base_path': str(settings.DATA_DIR),
        'download_url': reverse('configuration:download_database'),
        'db_size': format_file_size(db_size),
        'db_limit': format_file_size(DB_LIMIT),
        'db_percent': db_percent,
        'db_color': db_color,
    }

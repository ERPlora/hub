"""
Main Files Views

Local file browser and database download page.
"""
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from config.paths import get_data_paths


@login_required
@htmx_view('main/files/pages/index.html', 'main/files/partials/content.html')
def index(request):
    """Files management page - browse local files and download database."""
    paths = get_data_paths()

    return {
        'current_section': 'files',
        'page_title': 'Files',
        'base_path': str(paths.base_dir),
    }

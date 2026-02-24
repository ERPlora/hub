"""
Local Files Views - File Browser and Database Download.

Provides file browser for local Hub data (media, modules, reports, backups)
and database download functionality.
"""
import os
import mimetypes
from pathlib import Path
from datetime import datetime

from django.conf import settings as django_settings
from django.http import HttpResponse, FileResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from apps.accounts.decorators import login_required


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_file_icon(filename: str, is_dir: bool = False) -> str:
    """Get icon name for file type."""
    if is_dir:
        return 'folder'

    ext = Path(filename).suffix.lower()

    icon_map = {
        # Images
        '.jpg': 'image', '.jpeg': 'image', '.png': 'image',
        '.gif': 'image', '.webp': 'image', '.svg': 'image',
        # Documents
        '.pdf': 'document-text', '.doc': 'document-text',
        '.docx': 'document-text', '.txt': 'document-text',
        # Spreadsheets
        '.xls': 'grid', '.xlsx': 'grid', '.csv': 'grid',
        # Code
        '.py': 'code-slash', '.js': 'code-slash', '.html': 'code-slash',
        '.css': 'code-slash', '.json': 'code-slash',
        # Archives
        '.zip': 'archive', '.tar': 'archive', '.gz': 'archive',
        '.rar': 'archive', '.7z': 'archive',
        # Database
        '.sqlite3': 'server', '.db': 'server', '.sqlite': 'server',
        # Logs
        '.log': 'list',
    }

    return icon_map.get(ext, 'document')


def get_allowed_directories() -> dict:
    """Get list of browsable directories with their display names."""
    return {
        'media': {'path': Path(django_settings.MEDIA_ROOT), 'name': 'Media Files', 'icon': 'images'},
        'modules': {'path': Path(django_settings.MODULES_DIR), 'name': 'Modules', 'icon': 'extension-puzzle'},
        'reports': {'path': Path(django_settings.REPORTS_DIR), 'name': 'Reports', 'icon': 'document-text'},
        'backups': {'path': Path(django_settings.BACKUPS_DIR), 'name': 'Backups', 'icon': 'cloud-download'},
        'logs': {'path': Path(django_settings.LOGS_DIR), 'name': 'Logs', 'icon': 'list'},
    }


@login_required
@require_GET
def download_database(request):
    """
    Download the SQLite database file.

    Returns the database as a downloadable file with timestamp in filename.
    """
    db_path = Path(django_settings.DATABASES['default']['NAME'])

    if not db_path.exists():
        return JsonResponse({'error': _('Database not found')}, status=404)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"hub_database_{timestamp}.sqlite3"

    # Return file as download
    response = FileResponse(
        open(db_path, 'rb'),
        as_attachment=True,
        filename=filename
    )
    response['Content-Type'] = 'application/x-sqlite3'

    return response


@login_required
@require_GET
def file_browser(request):
    """
    HTMX endpoint: Browse local files.

    Query params:
        - dir: Directory key (media, modules, reports, backups, logs)
        - path: Relative path within the directory
    """
    dir_key = request.GET.get('dir', 'media')
    rel_path = request.GET.get('path', '').strip('/')

    allowed_dirs = get_allowed_directories()

    if dir_key not in allowed_dirs:
        return HttpResponse(f'<p class="text-danger">{_("Invalid directory")}</p>', status=400)

    base_dir = allowed_dirs[dir_key]['path']
    current_dir = base_dir / rel_path if rel_path else base_dir

    # Security check: ensure path is within allowed directory
    try:
        current_dir = current_dir.resolve()
        base_dir = base_dir.resolve()
        if not str(current_dir).startswith(str(base_dir)):
            return HttpResponse(f'<p class="text-danger">{_("Access denied")}</p>', status=403)
    except Exception:
        return HttpResponse(f'<p class="text-danger">{_("Invalid path")}</p>', status=400)

    # Get files and folders
    items = []

    if current_dir.exists() and current_dir.is_dir():
        for item in sorted(current_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                stat = item.stat()
                items.append({
                    'name': item.name,
                    'is_dir': item.is_dir(),
                    'size': format_file_size(stat.st_size) if not item.is_dir() else '-',
                    'size_bytes': stat.st_size if not item.is_dir() else 0,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'icon': get_file_icon(item.name, item.is_dir()),
                    'path': str(item.relative_to(base_dir)),
                })
            except (PermissionError, OSError):
                continue

    # Build breadcrumbs
    breadcrumbs = [{'name': allowed_dirs[dir_key]['name'], 'path': ''}]
    if rel_path:
        parts = rel_path.split('/')
        current_crumb = ''
        for part in parts:
            current_crumb = f"{current_crumb}/{part}" if current_crumb else part
            breadcrumbs.append({'name': part, 'path': current_crumb})

    # Render HTML
    html = render_to_string('configuration/partials/file_browser_content.html', {
        'items': items,
        'dir_key': dir_key,
        'rel_path': rel_path,
        'breadcrumbs': breadcrumbs,
        'has_parent': bool(rel_path),
        'parent_path': '/'.join(rel_path.split('/')[:-1]) if rel_path else '',
        'is_empty': len(items) == 0,
        'directories': allowed_dirs,
    })

    return HttpResponse(html)


@login_required
@require_GET
def download_file(request):
    """
    Download a specific file from allowed directories.

    Query params:
        - dir: Directory key
        - path: Relative path to file
    """
    dir_key = request.GET.get('dir', '')
    rel_path = request.GET.get('path', '').strip('/')

    if not dir_key or not rel_path:
        return JsonResponse({'error': _('Missing parameters')}, status=400)

    allowed_dirs = get_allowed_directories()

    if dir_key not in allowed_dirs:
        return JsonResponse({'error': _('Invalid directory')}, status=400)

    base_dir = allowed_dirs[dir_key]['path']
    file_path = base_dir / rel_path

    # Security check
    try:
        file_path = file_path.resolve()
        base_dir = base_dir.resolve()
        if not str(file_path).startswith(str(base_dir)):
            return JsonResponse({'error': _('Access denied')}, status=403)
    except Exception:
        return JsonResponse({'error': _('Invalid path')}, status=400)

    if not file_path.exists() or not file_path.is_file():
        return JsonResponse({'error': _('File not found')}, status=404)

    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = 'application/octet-stream'

    # Return file
    response = FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename=file_path.name
    )
    response['Content-Type'] = content_type

    return response


@login_required
@require_GET
def file_preview(request):
    """
    HTMX endpoint: Preview a file inline.

    Returns HTML partial with preview content based on file type:
    - Images: <img> tag
    - PDF: <iframe>
    - Text/code/logs: content in <pre> (first 500 lines)
    - Other: file info + download button

    Query params:
        - dir: Directory key
        - path: Relative path to file
    """
    dir_key = request.GET.get('dir', '')
    rel_path = request.GET.get('path', '').strip('/')

    if not dir_key or not rel_path:
        return HttpResponse('<p class="text-error text-sm">Missing parameters</p>', status=400)

    allowed_dirs = get_allowed_directories()

    if dir_key not in allowed_dirs:
        return HttpResponse('<p class="text-error text-sm">Invalid directory</p>', status=400)

    base_dir = allowed_dirs[dir_key]['path']
    file_path = base_dir / rel_path

    # Security check
    try:
        file_path = file_path.resolve()
        base_dir = base_dir.resolve()
        if not str(file_path).startswith(str(base_dir)):
            return HttpResponse('<p class="text-error text-sm">Access denied</p>', status=403)
    except Exception:
        return HttpResponse('<p class="text-error text-sm">Invalid path</p>', status=400)

    if not file_path.exists() or not file_path.is_file():
        return HttpResponse('<p class="text-error text-sm">File not found</p>', status=404)

    stat = file_path.stat()
    content_type, _ = mimetypes.guess_type(str(file_path))
    ext = file_path.suffix.lower()

    context = {
        'file_name': file_path.name,
        'file_size': format_file_size(stat.st_size),
        'file_modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
        'file_icon': get_file_icon(file_path.name),
        'dir_key': dir_key,
        'file_path': rel_path,
        'content_type': content_type or 'application/octet-stream',
        'ext': ext,
    }

    # Determine preview type
    image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
    text_exts = {'.txt', '.log', '.csv', '.py', '.js', '.html', '.css', '.json', '.xml', '.md', '.yml', '.yaml', '.ini', '.cfg', '.conf', '.sh', '.sql'}
    pdf_exts = {'.pdf'}

    if ext in image_exts:
        context['preview_type'] = 'image'
    elif ext in pdf_exts:
        context['preview_type'] = 'pdf'
    elif ext in text_exts:
        context['preview_type'] = 'text'
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()[:500]
                context['text_content'] = ''.join(lines)
                context['total_lines'] = len(lines)
                if len(lines) == 500:
                    context['truncated'] = True
        except Exception:
            context['preview_type'] = 'binary'
    else:
        context['preview_type'] = 'binary'

    html = render_to_string('configuration/partials/file_preview.html', context)
    return HttpResponse(html)


@login_required
@require_GET
def serve_file(request):
    """
    Serve a file inline (not as download) for preview purposes.

    Used by image <img> tags and PDF <iframe> elements.
    """
    dir_key = request.GET.get('dir', '')
    rel_path = request.GET.get('path', '').strip('/')

    if not dir_key or not rel_path:
        return JsonResponse({'error': _('Missing parameters')}, status=400)

    allowed_dirs = get_allowed_directories()

    if dir_key not in allowed_dirs:
        return JsonResponse({'error': _('Invalid directory')}, status=400)

    base_dir = allowed_dirs[dir_key]['path']
    file_path = base_dir / rel_path

    # Security check
    try:
        file_path = file_path.resolve()
        base_dir = base_dir.resolve()
        if not str(file_path).startswith(str(base_dir)):
            return JsonResponse({'error': _('Access denied')}, status=403)
    except Exception:
        return JsonResponse({'error': _('Invalid path')}, status=400)

    if not file_path.exists() or not file_path.is_file():
        return JsonResponse({'error': _('File not found')}, status=404)

    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = 'application/octet-stream'

    response = FileResponse(
        open(file_path, 'rb'),
        content_type=content_type,
    )
    # Serve inline, not as download
    response['Content-Disposition'] = f'inline; filename="{file_path.name}"'
    return response


@login_required
@require_GET
def get_storage_info(request):
    """
    HTMX endpoint: Get storage information for all directories.

    Returns HTML with storage stats.
    """
    def get_dir_size(path: Path) -> int:
        """Calculate total size of directory."""
        total = 0
        if path.exists():
            for item in path.rglob('*'):
                if item.is_file():
                    try:
                        total += item.stat().st_size
                    except (PermissionError, OSError):
                        pass
        return total

    def count_files(path: Path) -> int:
        """Count files in directory."""
        count = 0
        if path.exists():
            for item in path.rglob('*'):
                if item.is_file():
                    count += 1
        return count

    # Get database size (recommended limit: 2 GB)
    db_path = Path(django_settings.DATABASES['default']['NAME'])
    db_size = db_path.stat().st_size if db_path.exists() else 0
    db_limit = 2 * 1024 * 1024 * 1024  # 2 GB
    db_percent = min(100, int((db_size / db_limit) * 100)) if db_limit else 0
    # Color: green < 1 GB, yellow 1-1.7 GB, red > 1.7 GB
    if db_size < 1 * 1024 * 1024 * 1024:
        db_color = 'success'
    elif db_size < 1.7 * 1024 * 1024 * 1024:
        db_color = 'warning'
    else:
        db_color = 'error'

    # Get directory sizes
    storage_info = {
        'database': {
            'name': 'Database',
            'icon': 'server',
            'size': format_file_size(db_size),
            'size_bytes': db_size,
            'files': 1 if db_path.exists() else 0,
            'limit': format_file_size(db_limit),
            'percent': db_percent,
            'color': db_color,
        },
        'media': {
            'name': 'Media Files',
            'icon': 'images',
            'size': format_file_size(get_dir_size(Path(django_settings.MEDIA_ROOT))),
            'size_bytes': get_dir_size(Path(django_settings.MEDIA_ROOT)),
            'files': count_files(Path(django_settings.MEDIA_ROOT)),
        },
        'modules': {
            'name': 'Modules',
            'icon': 'extension-puzzle',
            'size': format_file_size(get_dir_size(Path(django_settings.MODULES_DIR))),
            'size_bytes': get_dir_size(Path(django_settings.MODULES_DIR)),
            'files': count_files(Path(django_settings.MODULES_DIR)),
        },
        'reports': {
            'name': 'Reports',
            'icon': 'document-text',
            'size': format_file_size(get_dir_size(Path(django_settings.REPORTS_DIR))),
            'size_bytes': get_dir_size(Path(django_settings.REPORTS_DIR)),
            'files': count_files(Path(django_settings.REPORTS_DIR)),
        },
        'backups': {
            'name': 'Backups',
            'icon': 'cloud-download',
            'size': format_file_size(get_dir_size(Path(django_settings.BACKUPS_DIR))),
            'size_bytes': get_dir_size(Path(django_settings.BACKUPS_DIR)),
            'files': count_files(Path(django_settings.BACKUPS_DIR)),
        },
        'logs': {
            'name': 'Logs',
            'icon': 'list',
            'size': format_file_size(get_dir_size(Path(django_settings.LOGS_DIR))),
            'size_bytes': get_dir_size(Path(django_settings.LOGS_DIR)),
            'files': count_files(Path(django_settings.LOGS_DIR)),
        },
    }

    # Calculate total
    total_size = sum(info['size_bytes'] for info in storage_info.values())
    total_files = sum(info['files'] for info in storage_info.values())

    html = render_to_string('configuration/partials/storage_info.html', {
        'storage_info': storage_info,
        'total_size': format_file_size(total_size),
        'total_files': total_files,
        'base_path': str(django_settings.DATA_DIR),
    })

    return HttpResponse(html)

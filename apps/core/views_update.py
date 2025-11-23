"""
Update notification views for CPOS Hub.

Provides UI for displaying update notifications and managing updates.
"""

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .update_manager import update_manager
import logging

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def check_updates(request):
    """
    Check for available updates and return JSON response.

    Returns:
        JSON with update information
    """
    result = update_manager.check_for_updates()
    return JsonResponse(result)


@require_http_methods(["GET"])
def update_status(request):
    """
    Get current update status.

    Returns:
        JSON with current version and last check info
    """
    state = update_manager.get_state()

    return JsonResponse({
        'current_version': update_manager.current_version,
        'os': update_manager.os_type,
        'last_check': state.get('last_check') if state else None,
        'update_available': state.get('update_available', False) if state else False,
        'latest_version': state.get('latest_version') if state else None,
    })


@require_http_methods(["POST"])
def download_update(request):
    """
    Download an available update.

    Expected POST data:
        download_url: URL to download from
        version: Target version
        checksum: Optional SHA256 checksum for verification

    Returns:
        JSON with download result
    """
    import json
    data = json.loads(request.body)

    download_url = data.get('download_url')
    target_version = data.get('version')
    expected_checksum = data.get('checksum')

    if not download_url or not target_version:
        return JsonResponse({
            'success': False,
            'error': 'download_url and version are required'
        }, status=400)

    # Download
    success, file_path, error = update_manager.download_update(download_url, target_version)

    if not success:
        return JsonResponse({
            'success': False,
            'error': error,
        }, status=400)

    # Verify checksum if provided
    if expected_checksum:
        valid, verify_error = update_manager.verify_download(file_path, expected_checksum)
        if not valid:
            return JsonResponse({
                'success': False,
                'error': f'Checksum verification failed: {verify_error}',
            }, status=400)

    return JsonResponse({
        'success': True,
        'file_path': str(file_path) if file_path else None,
        'message': 'Update downloaded successfully',
    })


@require_http_methods(["POST"])
def install_update(request):
    """
    Install a downloaded update.

    Expected POST data:
        file_path: Path to downloaded update file
        version: Target version

    Returns:
        JSON with installation result
    """
    import json
    from pathlib import Path

    data = json.loads(request.body)

    file_path_str = data.get('file_path')
    target_version = data.get('version')

    if not file_path_str or not target_version:
        return JsonResponse({
            'success': False,
            'error': 'file_path and version are required'
        }, status=400)

    file_path = Path(file_path_str)

    if not file_path.exists():
        return JsonResponse({
            'success': False,
            'error': f'Update file not found: {file_path}'
        }, status=400)

    # Create backup
    logger.info("Creating backup before update...")
    backup_success, backup_path, backup_error = update_manager.create_backup(
        f"pre_update_{target_version}"
    )

    if not backup_success:
        return JsonResponse({
            'success': False,
            'error': f'Backup failed: {backup_error}',
        }, status=500)

    # Install update (prepare updater script)
    success, error = update_manager.install_update(file_path, target_version, backup_path)

    if not success:
        return JsonResponse({
            'success': False,
            'error': error,
        }, status=500)

    return JsonResponse({
        'success': True,
        'message': 'Update prepared successfully. Ready to apply.',
        'backup_path': str(backup_path),
    })


@require_http_methods(["POST"])
def apply_update(request):
    """
    Apply the prepared update and restart the Hub.

    This will:
    1. Launch the updater script
    2. Exit the Hub process
    3. Updater replaces files
    4. Updater restarts Hub

    Returns:
        JSON with result (or Hub exits immediately)
    """
    success, error = update_manager.apply_update()

    if not success:
        return JsonResponse({
            'success': False,
            'error': error,
        }, status=500)

    # If we reach here, something went wrong
    # (normally the Hub should exit before returning)
    return JsonResponse({
        'success': True,
        'message': 'Update script launched. Hub will restart shortly.',
    })


@require_http_methods(["POST"])
def rollback_update(request):
    """
    Rollback to a previous backup.

    Expected POST data:
        backup_path: Path to backup directory

    Returns:
        JSON with rollback result
    """
    import json
    from pathlib import Path

    data = json.loads(request.body)
    backup_path_str = data.get('backup_path')

    if not backup_path_str:
        return JsonResponse({
            'success': False,
            'error': 'backup_path is required'
        }, status=400)

    backup_path = Path(backup_path_str)

    success, error = update_manager.rollback_update(backup_path)

    if not success:
        return JsonResponse({
            'success': False,
            'error': error,
        }, status=500)

    return JsonResponse({
        'success': True,
        'message': 'Rollback completed successfully. Please restart the Hub.',
    })


@require_http_methods(["GET"])
def update_notification(request):
    """
    Render update notification banner (HTMX partial).

    This is loaded via HTMX and displays a banner if an update is available.
    """
    state = update_manager.get_state()

    if not state or not state.get('update_available'):
        # No update available - return empty response
        return render(request, 'core/update_notification_empty.html')

    context = {
        'current_version': update_manager.current_version,
        'latest_version': state.get('latest_version'),
        'update_type': 'minor',  # TODO: Get from state
    }

    return render(request, 'core/update_notification.html', context)

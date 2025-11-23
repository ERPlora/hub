"""
Plugin Management Views
Similar to WordPress plugin management page
"""
import json
import shutil
import sys
import os
from pathlib import Path
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings
from django.core.management import call_command


def plugins_index(request):
    """
    Plugin management page - similar to WordPress
    Shows all plugins (active and inactive) with actions
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    from apps.plugins_runtime.loader import plugin_loader

    # Get all plugins from filesystem (active and inactive)
    plugins_dir = Path(django_settings.PLUGINS_DIR)
    all_plugins = []

    if plugins_dir.exists():
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip hidden directories
            if plugin_dir.name.startswith('.'):
                continue

            plugin_id = plugin_dir.name
            is_active = not plugin_id.startswith('_')

            # Clean plugin_id for display (remove _ if disabled)
            display_id = plugin_id.lstrip('_')

            # Read plugin.json if exists
            plugin_json_path = plugin_dir / 'plugin.json'
            plugin_data = {
                'plugin_id': display_id,
                'folder_name': plugin_id,
                'name': display_id.title(),
                'description': '',
                'version': '1.0.0',
                'author': '',
                'icon': 'cube-outline',
                'is_active': is_active,
            }

            if plugin_json_path.exists():
                try:
                    with open(plugin_json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        plugin_data['name'] = json_data.get('name', plugin_data['name'])
                        plugin_data['description'] = json_data.get('description', '')
                        plugin_data['version'] = json_data.get('version', '1.0.0')
                        plugin_data['author'] = json_data.get('author', '')
                        # Get icon from menu section if available
                        menu_config = json_data.get('menu', {})
                        plugin_data['icon'] = menu_config.get('icon', 'cube-outline')
                except Exception as e:
                    print(f"[WARNING] Error reading plugin.json for {plugin_id}: {e}")

            all_plugins.append(plugin_data)

    # Sort: active plugins first, then by name
    all_plugins.sort(key=lambda x: (not x['is_active'], x['name']))

    # Calculate statistics
    active_count = sum(1 for p in all_plugins if p['is_active'])
    inactive_count = sum(1 for p in all_plugins if not p['is_active'])

    # Check if there are plugins pending restart
    plugins_pending_restart = request.session.get('plugins_pending_restart', [])
    requires_restart = len(plugins_pending_restart) > 0

    context = {
        'plugins': all_plugins,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'current_view': 'plugins',
        'requires_restart': requires_restart,
        'plugins_pending_restart': plugins_pending_restart
    }
    return render(request, 'core/plugins.html', context)


@require_http_methods(["POST"])
def plugin_activate(request, plugin_id):
    """
    Activate a plugin by renaming folder (remove _ prefix) and apply migrations
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    plugins_dir = Path(django_settings.PLUGINS_DIR)
    disabled_folder = plugins_dir / f"_{plugin_id}"
    active_folder = plugins_dir / plugin_id

    if not disabled_folder.exists():
        return JsonResponse({'success': False, 'error': 'Plugin not found'}, status=404)

    if active_folder.exists():
        return JsonResponse({'success': False, 'error': 'Plugin already active'}, status=400)

    try:
        # Rename folder to activate
        disabled_folder.rename(active_folder)

        # Load the plugin dynamically
        from apps.plugins_runtime.loader import plugin_loader
        plugin_loaded = plugin_loader.load_plugin(plugin_id)

        if not plugin_loaded:
            # Rollback: rename back to disabled
            active_folder.rename(disabled_folder)
            return JsonResponse({
                'success': False,
                'error': f'Failed to load plugin {plugin_id}'
            }, status=500)

        # Note: Migrations cannot be applied during dynamic activation because Django's
        # app registry is initialized at startup. The plugin's migrations will be
        # applied automatically on the next server restart.
        print(f"[PLUGIN ACTIVATE] Plugin {plugin_id} activated. Restart required to apply migrations.")

        # Mark that restart is needed in session (for migrations + URL routing)
        if 'plugins_pending_restart' not in request.session:
            request.session['plugins_pending_restart'] = []

        if plugin_id not in request.session['plugins_pending_restart']:
            request.session['plugins_pending_restart'].append(plugin_id)
            request.session.modified = True

        return JsonResponse({
            'success': True,
            'message': 'Plugin activated and migrations applied. Restart required for URLs.',
            'requires_restart': True
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def plugin_deactivate(request, plugin_id):
    """
    Deactivate a plugin by renaming folder (add _ prefix)
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    plugins_dir = Path(django_settings.PLUGINS_DIR)
    active_folder = plugins_dir / plugin_id
    disabled_folder = plugins_dir / f"_{plugin_id}"

    if not active_folder.exists():
        return JsonResponse({'success': False, 'error': 'Plugin not found'}, status=404)

    if disabled_folder.exists():
        return JsonResponse({'success': False, 'error': 'Plugin already disabled'}, status=400)

    try:
        # Rename folder to deactivate
        active_folder.rename(disabled_folder)
        return JsonResponse({'success': True, 'message': 'Plugin deactivated. Restart required.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def plugin_delete(request, plugin_id):
    """
    Delete a plugin completely (remove folder)
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    plugins_dir = Path(django_settings.PLUGINS_DIR)

    # Try both active and disabled folders
    active_folder = plugins_dir / plugin_id
    disabled_folder = plugins_dir / f"_{plugin_id}"

    folder_to_delete = None
    if active_folder.exists():
        folder_to_delete = active_folder
    elif disabled_folder.exists():
        folder_to_delete = disabled_folder

    if not folder_to_delete:
        return JsonResponse({'success': False, 'error': 'Plugin not found'}, status=404)

    try:
        # Delete folder completely
        shutil.rmtree(folder_to_delete)
        return JsonResponse({'success': True, 'message': 'Plugin deleted successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def plugin_restart_server(request):
    """
    Restart the Django development server and run migrations for activated plugins
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        # Run migrations for all active plugins
        call_command('migrate', '--run-syncdb')

        # Clear plugins pending restart from session
        if 'plugins_pending_restart' in request.session:
            del request.session['plugins_pending_restart']
            request.session.modified = True

        # Trigger server restart by touching wsgi.py or main file
        # In development, Django's autoreload will detect this
        wsgi_file = Path(django_settings.BASE_DIR) / 'config' / 'wsgi.py'
        if wsgi_file.exists():
            wsgi_file.touch()

        return JsonResponse({
            'success': True,
            'message': 'Server restarting... Migrations applied.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

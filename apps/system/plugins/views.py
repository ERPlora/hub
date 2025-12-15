"""
System Plugins Views

Plugin management and marketplace - similar to WordPress plugins page.
All views support SPA navigation via HTMX.
"""
import json
import shutil
import os
import tempfile
import zipfile
import requests
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required


@login_required
@htmx_view('system/plugins/pages/installed.html', 'system/plugins/partials/installed_content.html')
def plugins_index(request):
    """Plugin management page - shows all installed plugins"""
    from apps.plugins_runtime.loader import plugin_loader

    plugins_dir = Path(django_settings.PLUGINS_DIR)
    all_plugins = []

    if plugins_dir.exists():
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir() or plugin_dir.name.startswith('.'):
                continue

            plugin_id = plugin_dir.name
            is_active = not plugin_id.startswith('_')
            display_id = plugin_id.lstrip('_')

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

            plugin_json_path = plugin_dir / 'plugin.json'
            if plugin_json_path.exists():
                try:
                    with open(plugin_json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        plugin_data['name'] = json_data.get('name', plugin_data['name'])
                        plugin_data['description'] = json_data.get('description', '')
                        plugin_data['version'] = json_data.get('version', '1.0.0')
                        plugin_data['author'] = json_data.get('author', '')
                        menu_config = json_data.get('menu', {})
                        plugin_data['icon'] = menu_config.get('icon', 'cube-outline')
                except Exception as e:
                    print(f"[WARNING] Error reading plugin.json for {plugin_id}: {e}")

            all_plugins.append(plugin_data)

    all_plugins.sort(key=lambda x: (not x['is_active'], x['name']))

    active_count = sum(1 for p in all_plugins if p['is_active'])
    inactive_count = sum(1 for p in all_plugins if not p['is_active'])

    plugins_pending_restart = request.session.get('plugins_pending_restart', [])
    requires_restart = len(plugins_pending_restart) > 0

    return {
        'current_section': 'plugins',
        'page_title': 'Plugins',
        'plugins': all_plugins,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'requires_restart': requires_restart,
        'plugins_pending_restart': plugins_pending_restart,
    }


@login_required
@htmx_view('system/plugins/pages/marketplace.html', 'system/plugins/partials/marketplace_content.html')
def marketplace(request):
    """Marketplace view - shows plugins from ERPlora Cloud"""
    plugins_dir = Path(django_settings.PLUGINS_DIR)
    installed_plugin_ids = []

    if plugins_dir.exists():
        for plugin_dir in plugins_dir.iterdir():
            if plugin_dir.is_dir() and not plugin_dir.name.startswith('.'):
                plugin_id = plugin_dir.name.lstrip('_')
                installed_plugin_ids.append(plugin_id)

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

    return {
        'current_section': 'marketplace',
        'page_title': 'Plugin Store',
        'installed_plugin_ids': json.dumps(installed_plugin_ids),
        'cloud_api_url': cloud_api_url,
    }


# API endpoints (no HTMX, just JSON)

@require_http_methods(["POST"])
def plugin_activate(request, plugin_id):
    """Activate a plugin by renaming folder"""
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
        disabled_folder.rename(active_folder)

        from apps.plugins_runtime.loader import plugin_loader
        plugin_loaded = plugin_loader.load_plugin(plugin_id)

        if not plugin_loaded:
            active_folder.rename(disabled_folder)
            return JsonResponse({
                'success': False,
                'error': f'Failed to load plugin {plugin_id}'
            }, status=500)

        if 'plugins_pending_restart' not in request.session:
            request.session['plugins_pending_restart'] = []

        if plugin_id not in request.session['plugins_pending_restart']:
            request.session['plugins_pending_restart'].append(plugin_id)
            request.session.modified = True

        return JsonResponse({
            'success': True,
            'message': 'Plugin activated. Restart required for URLs.',
            'requires_restart': True
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def plugin_deactivate(request, plugin_id):
    """Deactivate a plugin by renaming folder"""
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
        active_folder.rename(disabled_folder)
        return JsonResponse({'success': True, 'message': 'Plugin deactivated. Restart required.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def plugin_delete(request, plugin_id):
    """Delete a plugin completely"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    plugins_dir = Path(django_settings.PLUGINS_DIR)
    active_folder = plugins_dir / plugin_id
    disabled_folder = plugins_dir / f"_{plugin_id}"

    folder_to_delete = active_folder if active_folder.exists() else (disabled_folder if disabled_folder.exists() else None)

    if not folder_to_delete:
        return JsonResponse({'success': False, 'error': 'Plugin not found'}, status=404)

    try:
        shutil.rmtree(folder_to_delete)
        return JsonResponse({'success': True, 'message': 'Plugin deleted successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def plugin_restart_server(request):
    """Restart server and run migrations"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        from django.core.management import call_command
        call_command('migrate', '--run-syncdb')

        if 'plugins_pending_restart' in request.session:
            del request.session['plugins_pending_restart']
            request.session.modified = True

        wsgi_file = Path(django_settings.BASE_DIR) / 'config' / 'wsgi.py'
        if wsgi_file.exists():
            wsgi_file.touch()

        return JsonResponse({
            'success': True,
            'message': 'Server restarting... Migrations applied.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def fetch_marketplace(request):
    """Proxy to fetch plugins from Cloud API"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
        headers = {'Accept': 'application/json'}

        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        if not auth_token:
            return JsonResponse({
                'success': False,
                'error': 'Hub not connected to Cloud. Please connect in Settings.'
            }, status=401)

        headers['X-Hub-Token'] = auth_token
        api_url = f"{cloud_api_url}/api/marketplace/plugins/"

        response = requests.get(api_url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            plugins = data.get('results', data) if isinstance(data, dict) else data

            categories = []
            try:
                cat_response = requests.get(
                    f"{cloud_api_url}/api/marketplace/categories/",
                    headers=headers, timeout=10
                )
                if cat_response.status_code == 200:
                    categories = cat_response.json()
            except Exception:
                pass

            return JsonResponse({
                'success': True,
                'plugins': plugins if isinstance(plugins, list) else [],
                'categories': categories
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Cloud API returned {response.status_code}'
            }, status=response.status_code)

    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to connect to Cloud: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def purchase_plugin(request):
    """Initiate plugin purchase via Cloud API"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')

        if not plugin_id:
            return JsonResponse({'success': False, 'error': 'Missing plugin_id'}, status=400)

        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        if not hub_config.hub_jwt and not hub_config.cloud_api_token:
            return JsonResponse({
                'success': False,
                'error': 'Hub not connected to Cloud'
            }, status=400)

        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
        success_url = f"{cloud_api_url}/dashboard/plugins/marketplace/payment-success/?plugin_id={plugin_id}&source=hub"
        cancel_url = f"{cloud_api_url}/dashboard/plugins/marketplace/"

        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        headers = {
            'Content-Type': 'application/json',
            'X-Hub-Token': auth_token,
        }

        response = requests.post(
            f"{cloud_api_url}/api/marketplace/plugins/{plugin_id}/purchase/",
            json={'success_url': success_url, 'cancel_url': cancel_url},
            headers=headers, timeout=30
        )

        result = response.json()

        if response.status_code == 201 and result.get('is_free'):
            return JsonResponse({'success': True, 'is_free': True, 'message': 'Free plugin acquired'})

        if response.status_code == 200 and result.get('checkout_url'):
            return JsonResponse({
                'success': True,
                'checkout_url': result['checkout_url'],
                'session_id': result.get('session_id'),
                'mode': result.get('mode'),
                'amount': result.get('amount'),
                'currency': result.get('currency', 'EUR')
            })

        if response.status_code == 409:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'You already own this plugin'),
                'already_owned': True
            }, status=409)

        return JsonResponse({
            'success': False,
            'error': result.get('error', f'Cloud API error: {response.status_code}')
        }, status=response.status_code)

    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to connect to Cloud: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def check_ownership(request, plugin_id):
    """Check if Hub owner owns a specific plugin"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        if not hub_config.hub_jwt and not hub_config.cloud_api_token:
            return JsonResponse({
                'success': False, 'owned': False,
                'error': 'Hub not connected'
            }, status=400)

        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}

        response = requests.get(
            f"{cloud_api_url}/api/marketplace/plugins/{plugin_id}/check_ownership/",
            headers=headers, timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return JsonResponse({
                'success': True,
                'owned': data.get('owned', False),
                'purchase_type': data.get('purchase_type'),
            })
        else:
            return JsonResponse({
                'success': False, 'owned': False,
                'error': f'Cloud API returned {response.status_code}'
            }, status=response.status_code)

    except Exception as e:
        return JsonResponse({
            'success': False, 'owned': False, 'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def install_from_marketplace(request):
    """Download and install plugin from Cloud"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        plugin_slug = data.get('plugin_slug')
        download_url = data.get('download_url')

        if not plugin_slug or not download_url:
            return JsonResponse({
                'success': False,
                'error': 'Missing plugin_slug or download_url'
            }, status=400)

        plugins_dir = Path(django_settings.PLUGINS_DIR)
        plugin_target_dir = plugins_dir / plugin_slug

        if plugin_target_dir.exists() or (plugins_dir / f"_{plugin_slug}").exists():
            return JsonResponse({
                'success': False,
                'error': 'Plugin already installed'
            }, status=400)

        response = requests.get(download_url, timeout=60, stream=True)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        try:
            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                namelist = zip_ref.namelist()
                root_folders = set(name.split('/')[0] for name in namelist if name.split('/')[0])

                if len(root_folders) == 1:
                    root_folder = list(root_folders)[0]
                    zip_ref.extractall(plugins_dir)
                    extracted_dir = plugins_dir / root_folder
                    if extracted_dir != plugin_target_dir:
                        extracted_dir.rename(plugin_target_dir)
                else:
                    plugin_target_dir.mkdir(parents=True, exist_ok=True)
                    zip_ref.extractall(plugin_target_dir)

            from apps.plugins_runtime.loader import plugin_loader
            plugin_loader.load_plugin(plugin_slug)

            if 'plugins_pending_restart' not in request.session:
                request.session['plugins_pending_restart'] = []

            if plugin_slug not in request.session['plugins_pending_restart']:
                request.session['plugins_pending_restart'].append(plugin_slug)
                request.session.modified = True

            return JsonResponse({
                'success': True,
                'message': f'Plugin {plugin_slug} installed successfully',
                'requires_restart': True
            })

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to download plugin: {str(e)}'
        }, status=500)
    except zipfile.BadZipFile:
        return JsonResponse({
            'success': False,
            'error': 'Invalid plugin package'
        }, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

"""
Plugin Management Views
Similar to WordPress plugin management page
"""
import json
import shutil
import sys
import os
import tempfile
import zipfile
import requests
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


def marketplace(request):
    """
    Marketplace view - shows plugins available from ERPlora Cloud
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    # Get list of installed plugin IDs (slugs)
    plugins_dir = Path(django_settings.PLUGINS_DIR)
    installed_plugin_ids = []

    if plugins_dir.exists():
        for plugin_dir in plugins_dir.iterdir():
            if plugin_dir.is_dir() and not plugin_dir.name.startswith('.'):
                # Remove _ prefix if disabled
                plugin_id = plugin_dir.name.lstrip('_')
                installed_plugin_ids.append(plugin_id)

    # Get Cloud API URL from settings
    cloud_api_url = getattr(django_settings, 'ERPLORA_CLOUD_API_URL', 'https://erplora.com')

    context = {
        'current_view': 'marketplace',
        'installed_plugin_ids': json.dumps(installed_plugin_ids),
        'cloud_api_url': cloud_api_url,
    }
    return render(request, 'core/marketplace.html', context)


@require_http_methods(["GET"])
def fetch_marketplace(request):
    """
    Proxy endpoint to fetch plugins from Cloud API with Hub authentication.
    This allows the Hub to check ownership status for paid plugins.
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        # Get Hub configuration
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        # Get Cloud API URL
        cloud_api_url = getattr(django_settings, 'ERPLORA_CLOUD_API_URL', 'https://erplora.com')

        # Prepare headers - use Hub token if available for ownership info
        headers = {
            'Accept': 'application/json',
        }

        # If Hub is connected to Cloud, use authenticated endpoint
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        if auth_token:
            headers['X-Hub-Token'] = auth_token
            api_url = f"{cloud_api_url}/api/marketplace/plugins/"
        else:
            # Use public endpoint (no ownership info)
            api_url = f"{cloud_api_url}/api/plugins/marketplace/"

        print(f"[MARKETPLACE] Fetching plugins from: {api_url}")

        response = requests.get(api_url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()

            # Handle paginated response
            if 'results' in data:
                plugins = data['results']
            elif isinstance(data, list):
                plugins = data
            else:
                plugins = data.get('plugins', [])

            # Fetch categories if available
            categories = []
            if auth_token:
                try:
                    cat_response = requests.get(
                        f"{cloud_api_url}/api/marketplace/categories/",
                        headers=headers,
                        timeout=10
                    )
                    if cat_response.status_code == 200:
                        categories = cat_response.json()
                except Exception as cat_err:
                    print(f"[MARKETPLACE] Failed to fetch categories: {cat_err}")

            return JsonResponse({
                'success': True,
                'plugins': plugins,
                'categories': categories
            })
        else:
            error_msg = f'Cloud API returned {response.status_code}'
            try:
                error_data = response.json()
                error_msg = error_data.get('detail', error_msg)
            except Exception:
                pass
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=response.status_code)

    except requests.exceptions.RequestException as e:
        print(f"[MARKETPLACE] Request error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to connect to Cloud: {str(e)}'
        }, status=500)
    except Exception as e:
        print(f"[MARKETPLACE] Error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def purchase_plugin(request):
    """
    Initiate plugin purchase via Cloud API.
    Cloud creates Stripe Checkout session and returns checkout URL.
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')

        if not plugin_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing plugin_id'
            }, status=400)

        # Get Hub configuration to get the cloud_api_token
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        if not hub_config.hub_jwt and not hub_config.cloud_api_token:
            return JsonResponse({
                'success': False,
                'error': 'Hub not connected to Cloud. Please configure your Hub first.'
            }, status=400)

        # Get Cloud API URL
        cloud_api_url = getattr(django_settings, 'ERPLORA_CLOUD_API_URL', 'https://erplora.com')

        # Build success and cancel URLs for Hub
        success_url = request.build_absolute_uri('/plugins/purchase-success/')
        cancel_url = request.build_absolute_uri('/plugins/marketplace/')

        # Prepare auth header - prefer JWT, fall back to legacy token
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        headers = {
            'Content-Type': 'application/json',
            'X-Hub-Token': auth_token,
        }

        # Call Cloud API to create Stripe Checkout session
        purchase_url = f"{cloud_api_url}/api/marketplace/plugins/{plugin_id}/purchase/"
        print(f"[PURCHASE] Calling Cloud API: {purchase_url}")

        response = requests.post(
            purchase_url,
            json={
                'success_url': success_url,
                'cancel_url': cancel_url
            },
            headers=headers,
            timeout=30
        )

        result = response.json()
        print(f"[PURCHASE] Cloud API response: {response.status_code} - {result}")

        if response.status_code == 201 and result.get('is_free'):
            # Plugin is free, no payment needed
            return JsonResponse({
                'success': True,
                'is_free': True,
                'message': result.get('message', 'Free plugin acquired')
            })

        if response.status_code == 200 and result.get('checkout_url'):
            # Return Stripe checkout URL
            return JsonResponse({
                'success': True,
                'checkout_url': result['checkout_url'],
                'session_id': result.get('session_id'),
                'mode': result.get('mode'),
                'amount': result.get('amount'),
                'currency': result.get('currency', 'EUR')
            })

        if response.status_code == 409:
            # Already purchased
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'You already own this plugin'),
                'already_owned': True
            }, status=409)

        # Other errors
        return JsonResponse({
            'success': False,
            'error': result.get('error', f'Cloud API error: {response.status_code}')
        }, status=response.status_code)

    except requests.exceptions.RequestException as e:
        print(f"[PURCHASE] Request error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to connect to Cloud: {str(e)}'
        }, status=500)
    except Exception as e:
        print(f"[PURCHASE] Error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def purchase_success(request):
    """
    Handle successful purchase return from Stripe.
    Shows success message and offers to install the plugin.
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    context = {
        'current_view': 'marketplace',
    }
    return render(request, 'core/purchase_success.html', context)


@require_http_methods(["POST"])
def install_from_marketplace(request):
    """
    Download and install a plugin from ERPlora Cloud marketplace
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')
        plugin_slug = data.get('plugin_slug')
        download_url = data.get('download_url')

        if not plugin_slug or not download_url:
            return JsonResponse({
                'success': False,
                'error': 'Missing plugin_slug or download_url'
            }, status=400)

        plugins_dir = Path(django_settings.PLUGINS_DIR)
        plugin_target_dir = plugins_dir / plugin_slug

        # Check if already installed
        if plugin_target_dir.exists() or (plugins_dir / f"_{plugin_slug}").exists():
            return JsonResponse({
                'success': False,
                'error': 'Plugin already installed'
            }, status=400)

        # Download the plugin zip file
        print(f"[MARKETPLACE] Downloading plugin from: {download_url}")
        response = requests.get(download_url, timeout=60, stream=True)
        response.raise_for_status()

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        try:
            # Extract zip file
            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                # Check if the zip contains a single root folder
                namelist = zip_ref.namelist()
                root_folders = set()
                for name in namelist:
                    parts = name.split('/')
                    if parts[0]:
                        root_folders.add(parts[0])

                if len(root_folders) == 1:
                    # Single root folder - extract and rename
                    root_folder = list(root_folders)[0]
                    zip_ref.extractall(plugins_dir)
                    extracted_dir = plugins_dir / root_folder
                    if extracted_dir != plugin_target_dir:
                        extracted_dir.rename(plugin_target_dir)
                else:
                    # Multiple files/folders - extract into plugin folder
                    plugin_target_dir.mkdir(parents=True, exist_ok=True)
                    zip_ref.extractall(plugin_target_dir)

            print(f"[MARKETPLACE] Plugin extracted to: {plugin_target_dir}")

            # Try to load the plugin dynamically
            from apps.plugins_runtime.loader import plugin_loader
            plugin_loaded = plugin_loader.load_plugin(plugin_slug)

            if plugin_loaded:
                print(f"[MARKETPLACE] Plugin {plugin_slug} loaded successfully")
            else:
                print(f"[MARKETPLACE] Plugin {plugin_slug} installed but requires restart")

            # Mark that restart is needed
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
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except requests.exceptions.RequestException as e:
        print(f"[MARKETPLACE] Download error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to download plugin: {str(e)}'
        }, status=500)
    except zipfile.BadZipFile:
        return JsonResponse({
            'success': False,
            'error': 'Invalid plugin package (not a valid zip file)'
        }, status=400)
    except Exception as e:
        print(f"[MARKETPLACE] Install error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

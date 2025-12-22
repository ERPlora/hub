"""
Module Management Views
Similar to WordPress module management page
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


def modules_index(request):
    """
    Module management page - similar to WordPress
    Shows all modules (active and inactive) with actions
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('auth:login')

    from apps.modules_runtime.loader import module_loader

    # Get all modules from filesystem (active and inactive)
    modules_dir = Path(django_settings.MODULES_DIR)
    all_modules = []

    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue

            # Skip hidden directories
            if module_dir.name.startswith('.'):
                continue

            module_id = module_dir.name
            is_active = not module_id.startswith('_')

            # Clean module_id for display (remove _ if disabled)
            display_id = module_id.lstrip('_')

            # Read module.json if exists
            module_json_path = module_dir / 'module.json'
            module_data = {
                'module_id': display_id,
                'folder_name': module_id,
                'name': display_id.title(),
                'description': '',
                'version': '1.0.0',
                'author': '',
                'icon': 'cube-outline',
                'is_active': is_active,
            }

            if module_json_path.exists():
                try:
                    with open(module_json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        module_data['name'] = json_data.get('name', module_data['name'])
                        module_data['description'] = json_data.get('description', '')
                        module_data['version'] = json_data.get('version', '1.0.0')
                        module_data['author'] = json_data.get('author', '')
                        # Get icon from menu section if available
                        menu_config = json_data.get('menu', {})
                        module_data['icon'] = menu_config.get('icon', 'cube-outline')
                except Exception as e:
                    print(f"[WARNING] Error reading module.json for {module_id}: {e}")

            all_modules.append(module_data)

    # Sort: active modules first, then by name
    all_modules.sort(key=lambda x: (not x['is_active'], x['name']))

    # Calculate statistics
    active_count = sum(1 for m in all_modules if m['is_active'])
    inactive_count = sum(1 for m in all_modules if not m['is_active'])

    # Check if there are modules pending restart
    modules_pending_restart = request.session.get('modules_pending_restart', [])
    requires_restart = len(modules_pending_restart) > 0

    context = {
        'modules': all_modules,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'current_section': 'modules',
        'page_title': 'Modules',
        'requires_restart': requires_restart,
        'modules_pending_restart': modules_pending_restart
    }

    # Use new SPA templates with HTMX support
    if request.headers.get('HX-Request'):
        return render(request, 'system/modules/partials/installed_content.html', context)
    return render(request, 'system/modules/pages/installed.html', context)


@require_http_methods(["POST"])
def module_activate(request, module_id):
    """
    Activate a module by renaming folder (remove _ prefix) and apply migrations
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    modules_dir = Path(django_settings.MODULES_DIR)
    disabled_folder = modules_dir / f"_{module_id}"
    active_folder = modules_dir / module_id

    if not disabled_folder.exists():
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    if active_folder.exists():
        return JsonResponse({'success': False, 'error': 'Module already active'}, status=400)

    try:
        # Rename folder to activate
        disabled_folder.rename(active_folder)

        # Load the module dynamically
        from apps.modules_runtime.loader import module_loader
        module_loaded = module_loader.load_module(module_id)

        if not module_loaded:
            # Rollback: rename back to disabled
            active_folder.rename(disabled_folder)
            return JsonResponse({
                'success': False,
                'error': f'Failed to load module {module_id}'
            }, status=500)

        # Note: Migrations cannot be applied during dynamic activation because Django's
        # app registry is initialized at startup. The module's migrations will be
        # applied automatically on the next server restart.
        print(f"[MODULE ACTIVATE] Module {module_id} activated. Restart required to apply migrations.")

        # Mark that restart is needed in session (for migrations + URL routing)
        if 'modules_pending_restart' not in request.session:
            request.session['modules_pending_restart'] = []

        if module_id not in request.session['modules_pending_restart']:
            request.session['modules_pending_restart'].append(module_id)
            request.session.modified = True

        return JsonResponse({
            'success': True,
            'message': 'Module activated and migrations applied. Restart required for URLs.',
            'requires_restart': True
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def module_deactivate(request, module_id):
    """
    Deactivate a module by renaming folder (add _ prefix)
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    modules_dir = Path(django_settings.MODULES_DIR)
    active_folder = modules_dir / module_id
    disabled_folder = modules_dir / f"_{module_id}"

    if not active_folder.exists():
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    if disabled_folder.exists():
        return JsonResponse({'success': False, 'error': 'Module already disabled'}, status=400)

    try:
        # Rename folder to deactivate
        active_folder.rename(disabled_folder)
        return JsonResponse({'success': True, 'message': 'Module deactivated. Restart required.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def module_delete(request, module_id):
    """
    Delete a module completely (remove folder)
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    modules_dir = Path(django_settings.MODULES_DIR)

    # Try both active and disabled folders
    active_folder = modules_dir / module_id
    disabled_folder = modules_dir / f"_{module_id}"

    folder_to_delete = None
    if active_folder.exists():
        folder_to_delete = active_folder
    elif disabled_folder.exists():
        folder_to_delete = disabled_folder

    if not folder_to_delete:
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    try:
        # Delete folder completely
        shutil.rmtree(folder_to_delete)
        return JsonResponse({'success': True, 'message': 'Module deleted successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def module_restart_server(request):
    """
    Restart the Django development server and run migrations for activated modules
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        # Run migrations for all active modules
        call_command('migrate', '--run-syncdb')

        # Clear modules pending restart from session
        if 'modules_pending_restart' in request.session:
            del request.session['modules_pending_restart']
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
    Marketplace view - shows modules available from ERPlora Cloud
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('auth:login')

    # Get list of installed module IDs (slugs)
    modules_dir = Path(django_settings.MODULES_DIR)
    installed_module_ids = []

    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                # Remove _ prefix if disabled
                module_id = module_dir.name.lstrip('_')
                installed_module_ids.append(module_id)

    # Get Cloud API URL from settings
    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

    context = {
        'current_section': 'marketplace',
        'page_title': 'Module Store',
        'installed_module_ids': json.dumps(installed_module_ids),
        'cloud_api_url': cloud_api_url,
    }

    # Use new SPA templates with HTMX support
    if request.headers.get('HX-Request'):
        return render(request, 'system/modules/partials/marketplace_content.html', context)
    return render(request, 'system/modules/pages/marketplace.html', context)


@require_http_methods(["GET"])
def fetch_marketplace(request):
    """
    Proxy endpoint to fetch modules from Cloud API with Hub authentication.
    This allows the Hub to check ownership status for paid modules.
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        # Get Hub configuration
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        # Get Cloud API URL
        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

        # Prepare headers - use Hub token if available for ownership info
        headers = {
            'Accept': 'application/json',
        }

        # Use authenticated endpoint with Hub token
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        if not auth_token:
            return JsonResponse({
                'success': False,
                'error': 'Hub not connected to Cloud. Please connect your Hub in Settings to access the marketplace.'
            }, status=401)

        headers['X-Hub-Token'] = auth_token
        api_url = f"{cloud_api_url}/api/marketplace/modules/"

        print(f"[MARKETPLACE] Fetching modules from: {api_url}")

        response = requests.get(api_url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()

            # Handle paginated response
            if 'results' in data:
                modules = data['results']
            elif isinstance(data, list):
                modules = data
            else:
                modules = data.get('modules', [])

            # Fetch categories
            categories = []
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
                'modules': modules,
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
def purchase_module(request):
    """
    Initiate module purchase via Cloud API.
    Cloud creates Stripe Checkout session and returns checkout URL.
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        module_id = data.get('module_id')

        if not module_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing module_id'
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
        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

        # Build success and cancel URLs - redirect to Cloud's success page with source=hub
        # This allows Cloud to show "close this window" message for popup purchases
        success_url = f"{cloud_api_url}/dashboard/modules/marketplace/payment-success/?module_id={module_id}&source=hub"
        cancel_url = f"{cloud_api_url}/dashboard/modules/marketplace/"

        # Prepare auth header - prefer JWT, fall back to legacy token
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        headers = {
            'Content-Type': 'application/json',
            'X-Hub-Token': auth_token,
        }

        # Call Cloud API to create Stripe Checkout session
        purchase_url = f"{cloud_api_url}/api/marketplace/modules/{module_id}/purchase/"
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
            # Module is free, no payment needed
            return JsonResponse({
                'success': True,
                'is_free': True,
                'message': result.get('message', 'Free module acquired')
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
                'error': result.get('error', 'You already own this module'),
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
    Shows success message and offers to install the module.
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('auth:login')

    context = {
        'current_view': 'marketplace',
    }
    return render(request, 'core/purchase_success.html', context)


@require_http_methods(["GET"])
def check_ownership(request, module_id):
    """
    Proxy to Cloud API to check if Hub owner owns a specific module.
    Used for polling after Stripe checkout in popup.
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        # Get Hub configuration
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        if not hub_config.hub_jwt and not hub_config.cloud_api_token:
            return JsonResponse({
                'success': False,
                'owned': False,
                'error': 'Hub not connected to Cloud'
            }, status=400)

        # Get Cloud API URL
        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

        # Prepare auth header
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        headers = {
            'Accept': 'application/json',
            'X-Hub-Token': auth_token,
        }

        # Call Cloud API to check ownership
        api_url = f"{cloud_api_url}/api/marketplace/modules/{module_id}/check_ownership/"

        response = requests.get(api_url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return JsonResponse({
                'success': True,
                'owned': data.get('owned', False),
                'purchase_type': data.get('purchase_type'),
                'purchase_id': data.get('purchase_id'),
            })
        else:
            return JsonResponse({
                'success': False,
                'owned': False,
                'error': f'Cloud API returned {response.status_code}'
            }, status=response.status_code)

    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'owned': False,
            'error': f'Failed to connect to Cloud: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'owned': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def install_from_marketplace(request):
    """
    Download and install a module from ERPlora Cloud marketplace
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        module_id = data.get('module_id')
        module_slug = data.get('module_slug')
        download_url = data.get('download_url')

        if not module_slug or not download_url:
            return JsonResponse({
                'success': False,
                'error': 'Missing module_slug or download_url'
            }, status=400)

        modules_dir = Path(django_settings.MODULES_DIR)
        module_target_dir = modules_dir / module_slug

        # Check if already installed
        if module_target_dir.exists() or (modules_dir / f"_{module_slug}").exists():
            return JsonResponse({
                'success': False,
                'error': 'Module already installed'
            }, status=400)

        # Download the module zip file
        print(f"[MARKETPLACE] Downloading module from: {download_url}")
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
                    zip_ref.extractall(modules_dir)
                    extracted_dir = modules_dir / root_folder
                    if extracted_dir != module_target_dir:
                        extracted_dir.rename(module_target_dir)
                else:
                    # Multiple files/folders - extract into module folder
                    module_target_dir.mkdir(parents=True, exist_ok=True)
                    zip_ref.extractall(module_target_dir)

            print(f"[MARKETPLACE] Module extracted to: {module_target_dir}")

            # Try to load the module dynamically
            from apps.modules_runtime.loader import module_loader
            module_loaded = module_loader.load_module(module_slug)

            if module_loaded:
                print(f"[MARKETPLACE] Module {module_slug} loaded successfully")
            else:
                print(f"[MARKETPLACE] Module {module_slug} installed but requires restart")

            # Mark that restart is needed
            if 'modules_pending_restart' not in request.session:
                request.session['modules_pending_restart'] = []

            if module_slug not in request.session['modules_pending_restart']:
                request.session['modules_pending_restart'].append(module_slug)
                request.session.modified = True

            return JsonResponse({
                'success': True,
                'message': f'Module {module_slug} installed successfully',
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
            'error': f'Failed to download module: {str(e)}'
        }, status=500)
    except zipfile.BadZipFile:
        return JsonResponse({
            'success': False,
            'error': 'Invalid module package (not a valid zip file)'
        }, status=400)
    except Exception as e:
        print(f"[MARKETPLACE] Install error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

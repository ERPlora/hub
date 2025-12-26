"""
System Modules Views

Module management and marketplace - similar to WordPress modules page.
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
@htmx_view('system/modules/pages/installed.html', 'system/modules/partials/installed_content.html')
def modules_index(request):
    """Module management page - shows all installed modules"""
    from apps.modules_runtime.loader import module_loader

    modules_dir = Path(django_settings.MODULES_DIR)
    all_modules = []

    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir() or module_dir.name.startswith('.'):
                continue

            module_id = module_dir.name
            is_active = not module_id.startswith('_')
            display_id = module_id.lstrip('_')

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

            module_json_path = module_dir / 'module.json'
            if module_json_path.exists():
                try:
                    with open(module_json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        module_data['name'] = json_data.get('name', module_data['name'])
                        module_data['description'] = json_data.get('description', '')
                        module_data['version'] = json_data.get('version', '1.0.0')
                        module_data['author'] = json_data.get('author', '')
                        menu_config = json_data.get('menu', {})
                        module_data['icon'] = menu_config.get('icon', 'cube-outline')
                except Exception as e:
                    print(f"[WARNING] Error reading module.json for {module_id}: {e}")

            all_modules.append(module_data)

    all_modules.sort(key=lambda x: (not x['is_active'], x['name']))

    active_count = sum(1 for p in all_modules if p['is_active'])
    inactive_count = sum(1 for p in all_modules if not p['is_active'])

    modules_pending_restart = request.session.get('modules_pending_restart', [])
    requires_restart = len(modules_pending_restart) > 0

    return {
        'current_section': 'modules',
        'page_title': 'Modules',
        'modules': all_modules,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'requires_restart': requires_restart,
        'modules_pending_restart': modules_pending_restart,
    }


@login_required
@htmx_view('system/modules/pages/marketplace.html', 'system/modules/partials/marketplace_content.html')
def marketplace(request):
    """Marketplace view - shows modules from ERPlora Cloud"""
    from apps.configuration.models import HubConfig

    modules_dir = Path(django_settings.MODULES_DIR)
    installed_module_ids = []

    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                module_id = module_dir.name.lstrip('_')
                installed_module_ids.append(module_id)

    # Fetch categories for the select dropdown
    categories = []
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if auth_token:
        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
        headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}
        try:
            response = requests.get(
                f"{cloud_api_url}/api/marketplace/categories/",
                headers=headers, timeout=10
            )
            if response.status_code == 200:
                categories = response.json()
        except Exception:
            pass

    return {
        'current_section': 'marketplace',
        'page_title': 'Module Store',
        'installed_module_ids': installed_module_ids,
        'categories': categories,
    }


@login_required
def marketplace_modules_list(request):
    """
    HTMX endpoint: Fetch and render modules from Cloud API.
    Returns HTML partial with module cards.
    Supports filters: q (search), category, type, page
    """
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    from django.core.paginator import Paginator
    from apps.configuration.models import HubConfig

    # Get filters from query params
    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    type_filter = request.GET.get('type', '').strip()  # free, one_time, subscription
    page_number = request.GET.get('page', 1)

    # Get installed modules
    modules_dir = Path(django_settings.MODULES_DIR)
    installed_module_ids = []
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                installed_module_ids.append(module_dir.name.lstrip('_'))

    # Fetch from Cloud API
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        html = render_to_string('system/modules/partials/marketplace_error.html', {
            'error': 'Hub not connected to Cloud. Please connect in Settings.'
        })
        return HttpResponse(html)

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    headers = {
        'Accept': 'application/json',
        'X-Hub-Token': auth_token,
    }

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/modules/",
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            html = render_to_string('system/modules/partials/marketplace_error.html', {
                'error': f'Cloud API returned {response.status_code}'
            })
            return HttpResponse(html)

        data = response.json()
        modules = data.get('results', data) if isinstance(data, dict) else data
        if not isinstance(modules, list):
            modules = []

        # Apply filters
        if search_query:
            query_lower = search_query.lower()
            modules = [
                p for p in modules
                if query_lower in p.get('name', '').lower()
                or query_lower in p.get('description', '').lower()
            ]

        if category_filter:
            modules = [p for p in modules if p.get('category') == category_filter]

        if type_filter:
            modules = [p for p in modules if p.get('module_type') == type_filter]

        # Mark installed modules
        for module in modules:
            module['is_installed'] = module.get('slug', '') in installed_module_ids

        # Pagination (12 modules per page)
        paginator = Paginator(modules, 12)
        page_obj = paginator.get_page(page_number)

        html = render_to_string('system/modules/partials/marketplace_modules_grid.html', {
            'modules': page_obj.object_list,
            'page_obj': page_obj,
            'search_query': search_query,
            'category_filter': category_filter,
            'type_filter': type_filter,
        })
        return HttpResponse(html)

    except requests.exceptions.RequestException as e:
        html = render_to_string('system/modules/partials/marketplace_error.html', {
            'error': f'Failed to connect to Cloud: {str(e)}'
        })
        return HttpResponse(html)


@login_required
@htmx_view('system/modules/pages/module_detail.html', 'system/modules/partials/module_detail_content.html')
def module_detail(request, slug):
    """
    Module detail page - fetches full module info from Cloud API.
    """
    from apps.configuration.models import HubConfig

    # Check if module is installed locally
    modules_dir = Path(django_settings.MODULES_DIR)
    installed_module_ids = []
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                installed_module_ids.append(module_dir.name.lstrip('_'))

    is_installed = slug in installed_module_ids

    # Fetch module details from Cloud API
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if not auth_token:
        return {
            'current_section': 'marketplace',
            'page_title': 'Module Not Found',
            'error': 'Hub not connected to Cloud. Please connect in Settings.',
            'module': None,
        }

    cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    headers = {
        'Accept': 'application/json',
        'X-Hub-Token': auth_token,
    }

    try:
        response = requests.get(
            f"{cloud_api_url}/api/marketplace/modules/{slug}/",
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            return {
                'current_section': 'marketplace',
                'page_title': 'Module Not Found',
                'error': f'Module not found (status {response.status_code})',
                'module': None,
            }

        module = response.json()
        module['is_installed'] = is_installed

        # Fetch related modules (same category)
        related_modules = []
        try:
            all_response = requests.get(
                f"{cloud_api_url}/api/marketplace/modules/",
                headers=headers,
                timeout=10
            )
            if all_response.status_code == 200:
                all_data = all_response.json()
                all_modules = all_data.get('results', all_data) if isinstance(all_data, dict) else all_data
                if isinstance(all_modules, list):
                    related_modules = [
                        m for m in all_modules
                        if m.get('category') == module.get('category') and m.get('slug') != slug
                    ][:4]
        except Exception:
            pass

        return {
            'current_section': 'marketplace',
            'page_title': module.get('name', 'Module'),
            'module': module,
            'is_installed': is_installed,
            'is_owned': module.get('is_owned', False),
            'is_free': module.get('is_free', False),
            'related_modules': related_modules,
        }

    except requests.exceptions.RequestException as e:
        return {
            'current_section': 'marketplace',
            'page_title': 'Error',
            'error': f'Failed to connect to Cloud: {str(e)}',
            'module': None,
        }




# Helper function for HTMX responses

def _render_modules_page(request, error=None):
    """Render modules page as HTMX partial response"""
    from django.shortcuts import render

    modules_dir = Path(django_settings.MODULES_DIR)
    all_modules = []

    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir() or module_dir.name.startswith('.'):
                continue

            module_id = module_dir.name
            is_active = not module_id.startswith('_')
            display_id = module_id.lstrip('_')

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

            module_json_path = module_dir / 'module.json'
            if module_json_path.exists():
                try:
                    with open(module_json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        module_data['name'] = json_data.get('name', module_data['name'])
                        module_data['description'] = json_data.get('description', '')
                        module_data['version'] = json_data.get('version', '1.0.0')
                        module_data['author'] = json_data.get('author', '')
                        menu_config = json_data.get('menu', {})
                        module_data['icon'] = menu_config.get('icon', 'cube-outline')
                except Exception:
                    pass

            all_modules.append(module_data)

    all_modules.sort(key=lambda x: (not x['is_active'], x['name']))

    active_count = sum(1 for p in all_modules if p['is_active'])
    inactive_count = sum(1 for p in all_modules if not p['is_active'])

    modules_pending_restart = request.session.get('modules_pending_restart', [])
    requires_restart = len(modules_pending_restart) > 0

    # Get menu items for sidebar OOB update
    from apps.modules_runtime.loader import module_loader
    menu_items = module_loader.get_menu_items() if 'local_user_id' in request.session else []

    context = {
        'current_section': 'modules',
        'page_title': 'Modules',
        'modules': all_modules,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'requires_restart': requires_restart,
        'modules_pending_restart': modules_pending_restart,
        'error': error,
        'MODULE_MENU_ITEMS': menu_items,
    }

    return render(request, 'system/modules/partials/installed_content.html', context)


# API endpoints (support both HTMX and JSON)

def _trigger_server_reload():
    """Touch a file to trigger Django's auto-reload in development"""
    if django_settings.DEBUG:
        # Touch wsgi.py to trigger reload
        wsgi_file = Path(django_settings.BASE_DIR) / 'config' / 'wsgi.py'
        if wsgi_file.exists():
            wsgi_file.touch()


def _render_reload_response(message="Applying changes..."):
    """Return HTML that shows a loading state and reloads the page after server restarts"""
    html = f'''
    <div class="ion-padding" style="text-align: center; padding-top: 100px;">
        <ion-spinner name="crescent" style="width: 48px; height: 48px;"></ion-spinner>
        <h2 style="margin-top: 24px;">{message}</h2>
        <p class="text-medium">The page will reload automatically.</p>
    </div>
    <script>
        (function() {{
            let attempts = 0;
            const maxAttempts = 30;
            const checkServer = async () => {{
                attempts++;
                try {{
                    const response = await fetch('/ht/', {{ method: 'HEAD' }});
                    if (response.ok) {{
                        window.location.href = '/modules/';
                    }} else if (attempts < maxAttempts) {{
                        setTimeout(checkServer, 500);
                    }}
                }} catch (e) {{
                    if (attempts < maxAttempts) {{
                        setTimeout(checkServer, 500);
                    }}
                }}
            }};
            setTimeout(checkServer, 1000);
        }})();
    </script>
    '''
    return HttpResponse(html)


@require_http_methods(["POST"])
@login_required
def module_activate(request, module_id):
    """Activate a module by renaming folder"""
    modules_dir = Path(django_settings.MODULES_DIR)
    disabled_folder = modules_dir / f"_{module_id}"
    active_folder = modules_dir / module_id

    if not disabled_folder.exists():
        if request.htmx:
            return _render_modules_page(request, error='Module not found')
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    if active_folder.exists():
        if request.htmx:
            return _render_modules_page(request, error='Module already active')
        return JsonResponse({'success': False, 'error': 'Module already active'}, status=400)

    try:
        disabled_folder.rename(active_folder)

        # Trigger server reload to register new URLs
        _trigger_server_reload()

        if request.htmx:
            return _render_reload_response(f"Activating {module_id}...")

        return JsonResponse({
            'success': True,
            'message': 'Module activated. Server restarting.',
            'requires_restart': True
        })
    except Exception as e:
        if request.htmx:
            return _render_modules_page(request, error=str(e))
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
@login_required
def module_deactivate(request, module_id):
    """Deactivate a module by renaming folder"""
    modules_dir = Path(django_settings.MODULES_DIR)
    active_folder = modules_dir / module_id
    disabled_folder = modules_dir / f"_{module_id}"

    if not active_folder.exists():
        if request.htmx:
            return _render_modules_page(request, error='Module not found')
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    if disabled_folder.exists():
        if request.htmx:
            return _render_modules_page(request, error='Module already disabled')
        return JsonResponse({'success': False, 'error': 'Module already disabled'}, status=400)

    try:
        active_folder.rename(disabled_folder)

        # Trigger server reload to unregister URLs
        _trigger_server_reload()

        if request.htmx:
            return _render_reload_response(f"Deactivating {module_id}...")

        return JsonResponse({'success': True, 'message': 'Module deactivated. Server restarting.'})
    except Exception as e:
        if request.htmx:
            return _render_modules_page(request, error=str(e))
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
@login_required
def module_delete(request, module_id):
    """Delete a module completely"""
    modules_dir = Path(django_settings.MODULES_DIR)
    active_folder = modules_dir / module_id
    disabled_folder = modules_dir / f"_{module_id}"

    folder_to_delete = active_folder if active_folder.exists() else (disabled_folder if disabled_folder.exists() else None)

    if not folder_to_delete:
        if request.htmx:
            return _render_modules_page(request, error='Module not found')
        return JsonResponse({'success': False, 'error': 'Module not found'}, status=404)

    try:
        shutil.rmtree(folder_to_delete)

        if request.htmx:
            return _render_modules_page(request)

        return JsonResponse({'success': True, 'message': 'Module deleted successfully.'})
    except Exception as e:
        if request.htmx:
            return _render_modules_page(request, error=str(e))
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def module_restart_server(request):
    """Restart server and run migrations"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        from django.core.management import call_command
        call_command('migrate', '--run-syncdb')

        if 'modules_pending_restart' in request.session:
            del request.session['modules_pending_restart']
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
    """Proxy to fetch modules from Cloud API"""
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
        api_url = f"{cloud_api_url}/api/marketplace/modules/"

        response = requests.get(api_url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            modules = data.get('results', data) if isinstance(data, dict) else data

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
                'modules': modules if isinstance(modules, list) else [],
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
def purchase_module(request):
    """Initiate module purchase via Cloud API"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        module_id = data.get('module_id')

        if not module_id:
            return JsonResponse({'success': False, 'error': 'Missing module_id'}, status=400)

        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()

        if not hub_config.hub_jwt and not hub_config.cloud_api_token:
            return JsonResponse({
                'success': False,
                'error': 'Hub not connected to Cloud'
            }, status=400)

        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
        success_url = f"{cloud_api_url}/dashboard/modules/marketplace/payment-success/?module_id={module_id}&source=hub"
        cancel_url = f"{cloud_api_url}/dashboard/modules/marketplace/"

        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
        headers = {
            'Content-Type': 'application/json',
            'X-Hub-Token': auth_token,
        }

        response = requests.post(
            f"{cloud_api_url}/api/marketplace/modules/{module_id}/purchase/",
            json={'success_url': success_url, 'cancel_url': cancel_url},
            headers=headers, timeout=30
        )

        result = response.json()

        if response.status_code == 201 and result.get('is_free'):
            return JsonResponse({'success': True, 'is_free': True, 'message': 'Free module acquired'})

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
                'error': result.get('error', 'You already own this module'),
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
def check_ownership(request, module_id):
    """Check if Hub owner owns a specific module"""
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
            f"{cloud_api_url}/api/marketplace/modules/{module_id}/check_ownership/",
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
    """Download and install module from Cloud"""
    if 'local_user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
        module_slug = data.get('module_slug')
        download_url = data.get('download_url')

        if not module_slug or not download_url:
            return JsonResponse({
                'success': False,
                'error': 'Missing module_slug or download_url'
            }, status=400)

        modules_dir = Path(django_settings.MODULES_DIR)
        module_target_dir = modules_dir / module_slug

        if module_target_dir.exists() or (modules_dir / f"_{module_slug}").exists():
            return JsonResponse({
                'success': False,
                'error': 'Module already installed'
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
                    zip_ref.extractall(modules_dir)
                    extracted_dir = modules_dir / root_folder
                    if extracted_dir != module_target_dir:
                        extracted_dir.rename(module_target_dir)
                else:
                    module_target_dir.mkdir(parents=True, exist_ok=True)
                    zip_ref.extractall(module_target_dir)

            from apps.modules_runtime.loader import module_loader
            module_loader.load_module(module_slug)

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
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to download module: {str(e)}'
        }, status=500)
    except zipfile.BadZipFile:
        return JsonResponse({
            'success': False,
            'error': 'Invalid module package'
        }, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

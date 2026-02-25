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
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required


PER_PAGE_CHOICES = [10, 25, 50, 100]


@login_required
@htmx_view('system/modules/pages/installed.html', 'system/modules/partials/installed_content.html')
def modules_index(request):
    """Module management page - shows all installed modules with DataTable"""
    from django.shortcuts import render as django_render
    from django.core.paginator import Paginator
    from apps.modules_runtime.loader import module_loader
    import importlib

    search_query = request.GET.get('q', '').strip()
    sort_field = request.GET.get('sort', 'name')
    sort_dir = request.GET.get('dir', 'asc')
    current_view = request.GET.get('view', 'table')
    per_page = int(request.GET.get('per_page', 10))
    if per_page not in PER_PAGE_CHOICES:
        per_page = 10
    page_number = request.GET.get('page', 1)
    status_filter = request.GET.get('status', '')

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
                'category': 'default',
                'color': 'primary',
                'svg_path': '',
                'is_active': is_active,
            }

            # Check for SVG icon
            svg_icon_path = module_dir / 'static' / display_id / 'icons' / 'icon.svg'
            if svg_icon_path.exists():
                module_data['svg_path'] = f'/static/{display_id}/icons/icon.svg'

            # Try module.py first (preferred - supports translations)
            try:
                module_py = importlib.import_module(f"{display_id}.module")
                module_data['name'] = str(getattr(module_py, 'MODULE_NAME', module_data['name']))
                module_data['description'] = str(getattr(module_py, 'MODULE_DESCRIPTION', ''))
                module_data['version'] = getattr(module_py, 'MODULE_VERSION', '1.0.0')
                module_data['author'] = getattr(module_py, 'MODULE_AUTHOR', '')
                module_data['icon'] = getattr(module_py, 'MODULE_ICON', 'cube-outline')
                module_data['color'] = getattr(module_py, 'MODULE_COLOR', 'primary')
                module_data['category'] = getattr(module_py, 'MODULE_CATEGORY', 'default')
            except ImportError:
                pass  # No module.py found, use defaults

            all_modules.append(module_data)

    # Filter by search query
    if search_query:
        query_lower = search_query.lower()
        all_modules = [
            m for m in all_modules
            if query_lower in m['name'].lower()
            or query_lower in m['description'].lower()
            or query_lower in m['author'].lower()
            or query_lower in m['module_id'].lower()
        ]

    # Filter by status
    if status_filter == 'active':
        all_modules = [m for m in all_modules if m['is_active']]
    elif status_filter == 'inactive':
        all_modules = [m for m in all_modules if not m['is_active']]

    # Sort
    sort_key_map = {
        'name': lambda m: m['name'].lower(),
        'status': lambda m: (0 if m['is_active'] else 1, m['name'].lower()),
        'version': lambda m: m['version'],
        'author': lambda m: m['author'].lower(),
    }
    sort_fn = sort_key_map.get(sort_field, sort_key_map['name'])
    all_modules.sort(key=sort_fn, reverse=(sort_dir == 'desc'))

    active_count = sum(1 for p in all_modules if p['is_active'])
    inactive_count = sum(1 for p in all_modules if not p['is_active'])

    modules_pending_restart = request.session.get('modules_pending_restart', [])
    requires_restart = len(modules_pending_restart) > 0

    from django.urls import reverse

    # Add action URLs and slug to each module
    for module in all_modules:
        mid = module['module_id']
        module['slug'] = mid
        module['activate_url'] = reverse('mymodules:api_activate', kwargs={'module_id': mid})
        module['deactivate_url'] = reverse('mymodules:api_deactivate', kwargs={'module_id': mid})
        module['delete_url'] = reverse('mymodules:api_delete', kwargs={'module_id': mid})
        module['detail_url'] = reverse('mymodules:detail', kwargs={'slug': mid})

    # Paginate
    paginator = Paginator(all_modules, per_page)
    page_obj = paginator.get_page(page_number)

    context = {
        'modules': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'status_filter': status_filter,
        'current_view': current_view,
        'per_page': per_page,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'requires_restart': requires_restart,
        'modules_pending_restart': modules_pending_restart,
        'marketplace_url': reverse('marketplace:index'),
    }

    # HTMX partial: swap only datatable body (search, sort, filter, paginate)
    if request.htmx and request.htmx.target == 'datatable-body':
        return django_render(request, 'system/modules/partials/modules_list.html', context)

    context.update({
        'current_section': 'modules',
        'current_tab': 'installed',
        'page_title': 'My Modules',
    })
    return context


@login_required
@htmx_view('system/modules/pages/marketplace.html', 'system/modules/partials/marketplace_content.html')
def marketplace(request):
    """Marketplace view - shows modules from ERPlora Cloud"""
    from apps.configuration.models import HubConfig
    from config.module_categories import get_all_categories, get_all_industries

    modules_dir = Path(django_settings.MODULES_DIR)
    installed_module_ids = []

    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                module_id = module_dir.name.lstrip('_')
                installed_module_ids.append(module_id)

    # Get language for localized names
    language = getattr(request, 'LANGUAGE_CODE', 'en')[:2]

    # Get categories and industries from local config (fallback)
    categories = get_all_categories(language)
    industries = get_all_industries(language)

    # Fetch from Cloud API (source of truth for multi-language support)
    hub_config = HubConfig.get_solo()
    auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

    if auth_token:
        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
        headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}
        try:
            # Fetch categories from Cloud
            cat_response = requests.get(
                f"{cloud_api_url}/api/marketplace/categories/",
                headers=headers, params={'language': language}, timeout=10
            )
            if cat_response.status_code == 200:
                cloud_categories = cat_response.json()
                if cloud_categories:
                    categories = cloud_categories

            # Fetch industries from Cloud
            ind_response = requests.get(
                f"{cloud_api_url}/api/marketplace/industries/",
                headers=headers, params={'language': language}, timeout=10
            )
            if ind_response.status_code == 200:
                cloud_industries = ind_response.json()
                if cloud_industries:
                    industries = cloud_industries
        except Exception:
            # Fallback to local config if Cloud is unreachable
            pass

    return {
        'current_section': 'marketplace',
        'current_tab': 'marketplace',
        'page_title': 'Module Store',
        'installed_module_ids': installed_module_ids,
        'categories': categories,
        'industries': industries,
    }


@login_required
def marketplace_modules_list(request):
    """
    HTMX endpoint: Fetch and render modules from Cloud API.
    Returns HTML partial with module cards.
    Supports filters: q (search), category, industry, type, page
    """
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    from django.core.paginator import Paginator
    from apps.configuration.models import HubConfig

    # Get filters from query params
    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    industry_filter = request.GET.get('industry', '').strip()
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
            filtered_modules = []
            for p in modules:
                # Search in name
                if query_lower in p.get('name', '').lower():
                    filtered_modules.append(p)
                    continue
                # Search in description
                if query_lower in p.get('description', '').lower():
                    filtered_modules.append(p)
                    continue
                # Search in tags (list of strings)
                tags = p.get('tags', [])
                if isinstance(tags, list):
                    for tag in tags:
                        if query_lower in str(tag).lower():
                            filtered_modules.append(p)
                            break
            modules = filtered_modules

        if category_filter:
            modules = [p for p in modules if p.get('category') == category_filter]

        if industry_filter:
            filtered_modules = []
            for p in modules:
                industries = p.get('industries', [])
                if isinstance(industries, list) and industry_filter in industries:
                    filtered_modules.append(p)
            modules = filtered_modules

        if type_filter:
            modules = [p for p in modules if p.get('module_type') == type_filter]

        # Mark installed modules and add detail URL
        from django.urls import reverse
        for module in modules:
            module['is_installed'] = module.get('slug', '') in installed_module_ids
            module['detail_url'] = reverse('mymodules:detail', kwargs={'slug': module.get('slug', '')})

        # Pagination (12 modules per page)
        paginator = Paginator(modules, 12)
        page_obj = paginator.get_page(page_number)

        # Build pagination URLs with current filters
        def build_page_url(page_num):
            from django.urls import reverse
            base_url = reverse('mymodules:htmx_list')
            params = [f'page={page_num}']
            if search_query:
                params.append(f'q={search_query}')
            if category_filter:
                params.append(f'category={category_filter}')
            if industry_filter:
                params.append(f'industry={industry_filter}')
            if type_filter:
                params.append(f'type={type_filter}')
            return f"{base_url}?{'&'.join(params)}"

        html = render_to_string('system/modules/partials/marketplace_modules_grid.html', {
            'modules': page_obj.object_list,
            'page_obj': page_obj,
            'search_query': search_query,
            'category_filter': category_filter,
            'industry_filter': industry_filter,
            'type_filter': type_filter,
            'first_page_url': build_page_url(1),
            'prev_page_url': build_page_url(page_obj.previous_page_number()) if page_obj.has_previous() else None,
            'next_page_url': build_page_url(page_obj.next_page_number()) if page_obj.has_next() else None,
            'last_page_url': build_page_url(page_obj.paginator.num_pages),
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

    except requests.exceptions.RequestException:
        return {
            'current_section': 'marketplace',
            'page_title': 'No Connection',
            'no_connection': True,
            'module': None,
        }




# Helper function for HTMX responses

def _render_modules_page(request, error=None):
    """Render modules page as HTMX partial response (with DataTable context)"""
    from django.shortcuts import render
    from django.core.paginator import Paginator
    import importlib

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
                'category': 'default',
                'color': 'primary',
                'svg_path': '',
                'is_active': is_active,
            }

            # Check for SVG icon
            svg_icon_path = module_dir / 'static' / display_id / 'icons' / 'icon.svg'
            if svg_icon_path.exists():
                module_data['svg_path'] = f'/static/{display_id}/icons/icon.svg'

            # Try module.py first (preferred - supports translations)
            try:
                module_py = importlib.import_module(f"{display_id}.module")
                module_data['name'] = str(getattr(module_py, 'MODULE_NAME', module_data['name']))
                module_data['description'] = str(getattr(module_py, 'MODULE_DESCRIPTION', ''))
                module_data['version'] = getattr(module_py, 'MODULE_VERSION', '1.0.0')
                module_data['author'] = getattr(module_py, 'MODULE_AUTHOR', '')
                module_data['icon'] = getattr(module_py, 'MODULE_ICON', 'cube-outline')
                module_data['color'] = getattr(module_py, 'MODULE_COLOR', 'primary')
                module_data['category'] = getattr(module_py, 'MODULE_CATEGORY', 'default')
            except ImportError:
                pass  # No module.py found, use defaults

            all_modules.append(module_data)

    all_modules.sort(key=lambda x: (not x['is_active'], x['name']))

    active_count = sum(1 for p in all_modules if p['is_active'])
    inactive_count = sum(1 for p in all_modules if not p['is_active'])

    modules_pending_restart = request.session.get('modules_pending_restart', [])
    requires_restart = len(modules_pending_restart) > 0

    # Get menu items for sidebar OOB update
    from apps.modules_runtime.loader import module_loader
    menu_items = module_loader.get_menu_items() if 'local_user_id' in request.session else []

    # Add action URLs to each module
    from django.urls import reverse
    for module in all_modules:
        mid = module['module_id']
        module['slug'] = mid
        module['activate_url'] = reverse('mymodules:api_activate', kwargs={'module_id': mid})
        module['deactivate_url'] = reverse('mymodules:api_deactivate', kwargs={'module_id': mid})
        module['delete_url'] = reverse('mymodules:api_delete', kwargs={'module_id': mid})
        module['detail_url'] = reverse('mymodules:detail', kwargs={'slug': mid})

    # Paginate for DataTable
    per_page = 10
    paginator = Paginator(all_modules, per_page)
    page_obj = paginator.get_page(1)

    context = {
        'current_section': 'modules',
        'page_title': 'Modules',
        'modules': page_obj,
        'page_obj': page_obj,
        'sort_field': 'name',
        'sort_dir': 'asc',
        'current_view': 'table',
        'per_page': per_page,
        'search_query': '',
        'status_filter': '',
        'active_count': active_count,
        'inactive_count': inactive_count,
        'requires_restart': requires_restart,
        'modules_pending_restart': modules_pending_restart,
        'error': error,
        'MODULE_MENU_ITEMS': menu_items,
        'marketplace_url': reverse('marketplace:index'),
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


def _render_reload_response(message="Applying changes...", success_message="Module activated successfully"):
    """Return HTML that shows a loading spinner and reloads the page after server restarts"""
    html = f'''
    <div class="flex flex-col items-center justify-center py-24">
        <div class="loading" style="width: 48px; height: 48px;"></div>
        <h2 class="mt-6">{message}</h2>
        <p class="text-sm opacity-60">The page will reload automatically.</p>
    </div>
    <script>
        (function() {{
            if (typeof showToast === 'function') {{
                showToast('{message}', 'primary');
            }}

            var attempts = 0;
            var maxAttempts = 60;
            function checkServer() {{
                attempts++;
                fetch('/ht/', {{ method: 'HEAD', cache: 'no-store' }})
                    .then(function(response) {{
                        if (response.ok) {{
                            if (typeof showToast === 'function') {{
                                showToast('{success_message}', 'success');
                            }}
                            setTimeout(function() {{
                                window.location.href = '/modules/';
                            }}, 500);
                        }} else if (attempts < maxAttempts) {{
                            setTimeout(checkServer, 500);
                        }} else {{
                            window.location.href = '/modules/';
                        }}
                    }})
                    .catch(function() {{
                        if (attempts < maxAttempts) {{
                            setTimeout(checkServer, 500);
                        }} else {{
                            window.location.href = '/modules/';
                        }}
                    }});
            }}
            setTimeout(checkServer, 1500);
        }})();
    </script>
    '''
    return HttpResponse(html)


@require_http_methods(["POST"])
@login_required
def module_activate(request, module_id):
    """Activate a module by renaming folder and running migrations"""
    from django.core.management import call_command
    import io

    modules_dir = Path(django_settings.MODULES_DIR)
    disabled_folder = modules_dir / f"_{module_id}"
    active_folder = modules_dir / module_id

    if not disabled_folder.exists():
        if request.htmx:
            return _render_modules_page(request, error=_('Module not found'))
        return JsonResponse({'success': False, 'error': _('Module not found')}, status=404)

    if active_folder.exists():
        if request.htmx:
            return _render_modules_page(request, error=_('Module already active'))
        return JsonResponse({'success': False, 'error': _('Module already active')}, status=400)

    try:
        # Rename folder to activate
        disabled_folder.rename(active_folder)

        # Run migrations for the module
        try:
            output = io.StringIO()
            call_command('migrate', module_id, '--run-syncdb', stdout=output, stderr=output)
            migration_output = output.getvalue()
            if migration_output:
                print(f"[MODULES] Migrations for {module_id}: {migration_output}")
        except Exception as migrate_error:
            print(f"[MODULES] Migration error for {module_id}: {migrate_error}")
            # Continue anyway - migrations might not exist or already applied

        # Trigger server reload to register new URLs
        _trigger_server_reload()

        if request.htmx:
            return _render_reload_response(
                message=f"Activating {module_id}...",
                success_message=f"Module {module_id} activated successfully"
            )

        return JsonResponse({
            'success': True,
            'message': _('Module activated. Server restarting.'),
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
            return _render_modules_page(request, error=_('Module not found'))
        return JsonResponse({'success': False, 'error': _('Module not found')}, status=404)

    if disabled_folder.exists():
        if request.htmx:
            return _render_modules_page(request, error=_('Module already disabled'))
        return JsonResponse({'success': False, 'error': _('Module already disabled')}, status=400)

    try:
        active_folder.rename(disabled_folder)

        # Trigger server reload to unregister URLs
        _trigger_server_reload()

        if request.htmx:
            return _render_reload_response(
                message=f"Deactivating {module_id}...",
                success_message=f"Module {module_id} deactivated"
            )

        return JsonResponse({'success': True, 'message': _('Module deactivated. Server restarting.')})
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
            return _render_modules_page(request, error=_('Module not found'))
        return JsonResponse({'success': False, 'error': _('Module not found')}, status=404)

    try:
        shutil.rmtree(folder_to_delete)

        if request.htmx:
            return _render_modules_page(request)

        return JsonResponse({'success': True, 'message': _('Module deleted successfully.')})
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
            industries = []
            try:
                cat_response = requests.get(
                    f"{cloud_api_url}/api/marketplace/categories/",
                    headers=headers, timeout=10
                )
                if cat_response.status_code == 200:
                    categories = cat_response.json()

                ind_response = requests.get(
                    f"{cloud_api_url}/api/marketplace/industries/",
                    headers=headers, timeout=10
                )
                if ind_response.status_code == 200:
                    industries = ind_response.json()
            except Exception:
                pass

            return JsonResponse({
                'success': True,
                'modules': modules if isinstance(modules, list) else [],
                'categories': categories,
                'industries': industries
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
            return JsonResponse({'success': True, 'is_free': True, 'message': _('Free module acquired')})

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


@require_http_methods(["POST"])
@login_required
def rate_module(request):
    """Submit a module review (rating + optional comment) to Cloud API"""
    try:
        data = json.loads(request.body)
        module_id = data.get('module_id')
        rating = data.get('rating')
        comment = data.get('comment', '')

        if not module_id or not rating:
            return JsonResponse({'success': False, 'error': 'Missing module_id or rating'}, status=400)

        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_solo()
        auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

        if not auth_token:
            return JsonResponse({'success': False, 'error': 'Hub not connected to Cloud'}, status=401)

        cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
        response = requests.post(
            f"{cloud_api_url}/api/marketplace/modules/{module_id}/review/",
            json={'rating': rating, 'comment': comment},
            headers={'X-Hub-Token': auth_token, 'Content-Type': 'application/json'},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            return JsonResponse({
                'success': True,
                'message': 'Review submitted',
                'rating': result.get('rating'),
                'review_count': result.get('review_count'),
            })
        else:
            error = response.json().get('error', f'Cloud returned {response.status_code}')
            return JsonResponse({'success': False, 'error': error}, status=response.status_code)

    except requests.exceptions.RequestException:
        return JsonResponse({'success': False, 'error': 'Could not reach Cloud'}, status=503)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
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

        # Use module_id (local directory name) if provided, fall back to slug
        module_dir_name = data.get('module_id') or module_slug

        # Normalize http:// to https:// (Cloud URLs should always be HTTPS)
        if download_url.startswith('http://'):
            download_url = download_url.replace('http://', 'https://', 1)

        modules_dir = Path(django_settings.MODULES_DIR)
        module_target_dir = modules_dir / module_dir_name

        if module_target_dir.exists() or (modules_dir / f"_{module_dir_name}").exists():
            return JsonResponse({
                'success': False,
                'error': 'Module already installed'
            }, status=400)

        # Get Hub JWT token for authentication with Cloud
        from apps.configuration.models import HubConfig
        config = HubConfig.get_solo()
        if not config.hub_jwt:
            return JsonResponse({
                'success': False,
                'error': 'Hub not authenticated with Cloud. Please login again.'
            }, status=401)

        # Download with X-Hub-Token header
        headers = {
            'X-Hub-Token': config.hub_jwt
        }
        response = requests.get(download_url, headers=headers, timeout=60, stream=True)
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
            module_loader.load_module(module_dir_name)

            # Run migrations for the new module
            try:
                from django.core.management import call_command
                import io
                output = io.StringIO()
                call_command('migrate', module_dir_name, '--run-syncdb', stdout=output, stderr=output)
                migration_output = output.getvalue()
                if migration_output:
                    print(f"[MODULES] Migrations for {module_dir_name}: {migration_output}")
            except Exception as migrate_error:
                print(f"[MODULES] Migration error for {module_dir_name}: {migrate_error}")
                # Continue anyway - migrations might not exist

            if 'modules_pending_restart' not in request.session:
                request.session['modules_pending_restart'] = []

            if module_dir_name not in request.session['modules_pending_restart']:
                request.session['modules_pending_restart'].append(module_dir_name)
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

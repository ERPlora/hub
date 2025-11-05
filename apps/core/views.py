import json
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from .models import HubConfig, LocalUser, StoreConfig


def login(request):
    """
    Login page - supports both local PIN login and Cloud login
    """
    # Get all local users for employee selection
    local_users = LocalUser.objects.filter(is_active=True).order_by('name')

    # Convert to JSON for Alpine.js
    local_users_data = [
        {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'initials': user.get_initials(),
            'role': user.role.capitalize(),
            'roleColor': user.get_role_color(),
        }
        for user in local_users
    ]

    context = {
        'local_users_json': json.dumps(local_users_data),
    }

    return render(request, 'core/login.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def verify_pin(request):
    """
    Verify PIN for local user login
    """
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        pin = data.get('pin')

        if not user_id or not pin:
            return JsonResponse({'success': False, 'error': 'Missing data'})

        # Get user
        try:
            user = LocalUser.objects.get(id=user_id, is_active=True)
        except LocalUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'})

        # Verify PIN
        if user.check_pin(pin):
            # Update last login
            user.last_login = timezone.now()
            user.save()

            # Store user session
            request.session['local_user_id'] = user.id
            request.session['user_name'] = user.name
            request.session['user_email'] = user.email
            request.session['user_role'] = user.role
            request.session['user_language'] = user.language  # User's preferred language

            return JsonResponse({
                'success': True,
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'email': user.email,
                }
            })
        else:
            return JsonResponse({'success': False, 'error': 'Incorrect PIN'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def cloud_login(request):
    """
    Cloud login - authenticates against Cloud API and registers Hub if first time
    """
    try:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return JsonResponse({'success': False, 'error': 'Missing credentials'})

        # Call Cloud API to authenticate
        cloud_api_url = settings.CLOUD_API_URL

        try:
            response = requests.post(
                f"{cloud_api_url}/api/auth/login/",
                json={'email': email, 'password': password},
                timeout=10
            )

            if response.status_code == 200:
                auth_data = response.json()
                access_token = auth_data.get('access')

                # Get user info from Cloud
                user_response = requests.get(
                    f"{cloud_api_url}/api/auth/me/",
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10
                )

                if user_response.status_code == 200:
                    user_info = user_response.json()

                    # Check if Hub is configured
                    hub_config = HubConfig.get_config()

                    if not hub_config.is_configured:
                        # First time - register Hub with Cloud
                        hub_response = requests.post(
                            f"{cloud_api_url}/api/hubs/register/",
                            json={
                                'name': f"Hub - {email}",
                                'address': 'Local'
                            },
                            headers={'Authorization': f'Bearer {access_token}'},
                            timeout=10
                        )

                        if hub_response.status_code == 201:
                            hub_data = hub_response.json()

                            # Save Hub configuration
                            hub_config.hub_id = hub_data.get('hub_id')
                            hub_config.tunnel_port = hub_data.get('tunnel_port')
                            hub_config.tunnel_token = hub_data.get('tunnel_token')
                            hub_config.is_configured = True
                            hub_config.save()

                    # Get Hub config to use OS language as default
                    hub_config = HubConfig.get_config()

                    # Check if this is the first user in the Hub
                    is_first_user = LocalUser.objects.count() == 0

                    # Check if user already exists locally
                    local_user, created = LocalUser.objects.get_or_create(
                        cloud_user_id=user_info.get('id'),
                        defaults={
                            'email': email,
                            'name': user_info.get('name', email.split('@')[0]),
                            'role': 'admin' if is_first_user else 'cashier',  # First user is admin, others are cashier by default
                            'pin_hash': '',  # Will be set during PIN setup
                            'language': user_info.get('language', hub_config.os_language),  # Use Cloud language or OS language
                        }
                    )

                    # Check if user has PIN configured
                    first_time = not local_user.pin_hash

                    return JsonResponse({
                        'success': True,
                        'first_time': first_time,
                        'user': {
                            'id': local_user.id,
                            'name': local_user.name,
                            'email': local_user.email,
                        }
                    })
                else:
                    return JsonResponse({'success': False, 'error': 'Failed to get user info'})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid credentials'})

        except requests.exceptions.ConnectionError:
            return JsonResponse({'success': False, 'error': 'Cannot connect to Cloud. Check internet connection.'})
        except requests.exceptions.Timeout:
            return JsonResponse({'success': False, 'error': 'Connection timeout'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def setup_pin(request):
    """
    Setup PIN for first-time Cloud login user
    """
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        pin = data.get('pin')

        if not user_id or not pin:
            return JsonResponse({'success': False, 'error': 'Missing data'})

        # Validate PIN (4 digits)
        if len(pin) != 4 or not pin.isdigit():
            return JsonResponse({'success': False, 'error': 'PIN must be 4 digits'})

        # Get user
        try:
            user = LocalUser.objects.get(id=user_id)
        except LocalUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'})

        # Set PIN
        user.set_pin(pin)
        user.last_login = timezone.now()
        user.save()

        # Store user session
        request.session['local_user_id'] = user.id
        request.session['user_name'] = user.name
        request.session['user_email'] = user.email
        request.session['user_role'] = user.role
        request.session['user_language'] = user.language  # User's preferred language

        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def dashboard(request):
    """
    Dashboard view - placeholder for now
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('core:login')

    context = {
        'current_view': 'dashboard'
    }
    return render(request, 'core/dashboard.html', context)


def logout(request):
    """
    Logout - clear session
    """
    request.session.flush()
    return redirect('core:login')


def pos(request):
    """
    Point of Sale view - placeholder for now
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('core:login')

    context = {
        'current_view': 'pos'
    }
    return render(request, 'core/pos.html', context)


def settings(request):
    """
    Settings view
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('core:login')

    hub_config = HubConfig.get_config()
    store_config = StoreConfig.get_config()

    # Handle POST request for store configuration update
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_store':
            # Update store configuration
            store_config.business_name = request.POST.get('business_name', '').strip()
            store_config.business_address = request.POST.get('business_address', '').strip()
            store_config.vat_number = request.POST.get('vat_number', '').strip()
            store_config.phone = request.POST.get('phone', '').strip()
            store_config.email = request.POST.get('email', '').strip()
            store_config.website = request.POST.get('website', '').strip()

            # Tax configuration
            tax_rate = request.POST.get('tax_rate', '0.00')
            try:
                store_config.tax_rate = float(tax_rate) if tax_rate else 0.00
            except ValueError:
                store_config.tax_rate = 0.00

            store_config.tax_included = request.POST.get('tax_included') == 'on'

            # Handle logo upload
            if 'logo' in request.FILES:
                store_config.logo = request.FILES['logo']

            # Receipt configuration
            store_config.receipt_header = request.POST.get('receipt_header', '').strip()
            store_config.receipt_footer = request.POST.get('receipt_footer', '').strip()

            # Check if store is now complete
            store_config.is_configured = store_config.is_complete()

            store_config.save()

            # Store success message in session
            request.session['settings_message'] = 'Store configuration saved successfully'

            return redirect('core:settings')

    # Get success message if any
    settings_message = request.session.pop('settings_message', None)

    context = {
        'hub_config': hub_config,
        'store_config': store_config,
        'settings_message': settings_message,
        'current_view': 'settings'
    }
    return render(request, 'core/settings.html', context)


def employees(request):
    """
    Employees management view
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('core:login')

    local_users = LocalUser.objects.filter(is_active=True).order_by('name')
    context = {
        'local_users': local_users,
        'current_view': 'employees'
    }
    return render(request, 'core/employees.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_employee_create(request):
    """
    API: Create new employee
    """
    try:
        data = json.loads(request.body)
        name = data.get('name')
        email = data.get('email')
        role = data.get('role', 'cashier')
        pin = data.get('pin')

        if not name or not email or not pin:
            return JsonResponse({'success': False, 'error': 'Missing required fields'})

        # Check if email already exists
        if LocalUser.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'error': 'Email already exists'})

        # Create user (cloud_user_id will be synced later)
        user = LocalUser.objects.create(
            cloud_user_id=0,  # Temporary, will be updated when synced
            email=email,
            name=name,
            role=role
        )
        user.set_pin(pin)
        user.save()

        return JsonResponse({'success': True, 'user_id': user.id})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_employee_update(request):
    """
    API: Update employee
    """
    try:
        data = json.loads(request.body)
        user_id = data.get('id')
        name = data.get('name')
        email = data.get('email')
        role = data.get('role')

        if not user_id or not name or not email or not role:
            return JsonResponse({'success': False, 'error': 'Missing required fields'})

        user = LocalUser.objects.get(id=user_id)

        # Check if email changed and if it's already in use
        if user.email != email and LocalUser.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'error': 'Email already exists'})

        user.name = name
        user.email = email
        user.role = role
        user.save()

        return JsonResponse({'success': True})

    except LocalUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_employee_delete(request):
    """
    API: Delete employee (soft delete)
    """
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')

        if not user_id:
            return JsonResponse({'success': False, 'error': 'Missing user_id'})

        user = LocalUser.objects.get(id=user_id)

        # Prevent deleting admin users
        if user.role == 'admin':
            return JsonResponse({'success': False, 'error': 'Cannot delete admin users'})

        user.is_active = False
        user.save()

        return JsonResponse({'success': True})

    except LocalUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_employee_reset_pin(request):
    """
    API: Reset employee PIN
    """
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        pin = data.get('pin')

        if not user_id or not pin:
            return JsonResponse({'success': False, 'error': 'Missing required fields'})

        user = LocalUser.objects.get(id=user_id)
        user.set_pin(pin)
        user.save()

        return JsonResponse({'success': True})

    except LocalUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ============================================================================
# Plugin Management Views
# ============================================================================

def plugins(request):
    """
    Plugins management view - list installed and available plugins
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('core:login')

    from .plugin_loader import plugin_loader
    from .models import Plugin

    # Get all installed plugins
    installed_plugins = Plugin.objects.filter(is_installed=True).order_by('name')

    # Get discovered plugins (from filesystem)
    discovered = plugin_loader.discover_plugins()

    context = {
        'installed_plugins': installed_plugins,
        'discovered_count': len(discovered),
        'current_view': 'plugins'
    }
    return render(request, 'core/plugins.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_plugin_install(request):
    """
    API: Install plugin from uploaded ZIP file
    """
    try:
        # Check if file was uploaded
        if 'plugin_zip' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})

        plugin_file = request.FILES['plugin_zip']

        # Validate file extension
        if not plugin_file.name.endswith('.zip'):
            return JsonResponse({'success': False, 'error': 'File must be a ZIP archive'})

        # Save uploaded file to temp directory (cross-platform)
        from .runtime_manager import plugin_runtime_manager

        # Use runtime manager's temp directory (works on Windows, macOS, Linux)
        tmp_file_path = plugin_runtime_manager.get_temp_file_path(plugin_file.name)

        # Write uploaded file to temp location
        with open(tmp_file_path, 'wb') as tmp_file:
            for chunk in plugin_file.chunks():
                tmp_file.write(chunk)

        # Install plugin using runtime manager
        # Note: The ZIP file is automatically deleted after extraction
        result = plugin_runtime_manager.install_plugin_from_zip(str(tmp_file_path))

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_plugin_activate(request):
    """
    API: Activate/deactivate a plugin
    """
    try:
        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')
        activate = data.get('activate', True)

        if not plugin_id:
            return JsonResponse({'success': False, 'error': 'Missing plugin_id'})

        from .models import Plugin
        from .plugin_loader import plugin_loader

        plugin = Plugin.objects.get(plugin_id=plugin_id)

        if activate:
            # Activate and load plugin
            plugin.is_active = True
            plugin.save()

            if plugin_loader.load_plugin(plugin_id):
                return JsonResponse({'success': True, 'message': f'Plugin {plugin_id} activated'})
            else:
                return JsonResponse({'success': False, 'error': 'Failed to load plugin'})
        else:
            # Deactivate plugin
            if plugin_loader.unload_plugin(plugin_id):
                return JsonResponse({'success': True, 'message': f'Plugin {plugin_id} deactivated'})
            else:
                return JsonResponse({'success': False, 'error': 'Failed to deactivate plugin'})

    except Plugin.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Plugin not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_plugin_uninstall(request):
    """
    API: Uninstall a plugin
    """
    try:
        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')

        if not plugin_id:
            return JsonResponse({'success': False, 'error': 'Missing plugin_id'})

        from .runtime_manager import plugin_runtime_manager

        result = plugin_runtime_manager.uninstall_plugin(plugin_id)

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["GET"])
def api_plugins_list(request):
    """
    API: List all plugins with their status
    """
    try:
        from .models import Plugin

        plugins = Plugin.objects.all().order_by('name')
        plugins_data = []

        for plugin in plugins:
            plugins_data.append({
                'plugin_id': plugin.plugin_id,
                'name': plugin.name,
                'description': plugin.description,
                'version': plugin.version,
                'author': plugin.author,
                'icon': plugin.icon,
                'category': plugin.category,
                'is_installed': plugin.is_installed,
                'is_active': plugin.is_active,
                'show_in_menu': plugin.show_in_menu,
                'menu_label': plugin.menu_label,
                'menu_icon': plugin.menu_icon,
                'menu_order': plugin.menu_order,
            })

        return JsonResponse({'success': True, 'plugins': plugins_data})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

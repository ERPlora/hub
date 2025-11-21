import json
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings as django_settings
from .models import LocalUser
from apps.configuration.models import HubConfig
from apps.sync.models import TokenCache


# Helper functions

def verify_user_access_with_cloud(user):
    """
    Verificar si el usuario tiene acceso activo al Hub consultando Cloud.

    Se ejecuta durante el login para sincronizar el estado del usuario.
    Si el Hub está offline, se confía en el estado local.

    Args:
        user: LocalUser instance

    Returns:
        tuple: (has_access: bool, reason: str)
    """
    hub_config = HubConfig.get_config()

    # Si Hub no está configurado, permitir acceso local
    if not hub_config.is_configured:
        return True, "hub_not_configured"

    try:
        # Consultar estado del usuario en Cloud
        response = requests.get(
            f"{django_settings.CLOUD_API_URL}/api/hubs/{hub_config.hub_id}/users/check/{user.email}/",
            headers={'X-Hub-Token': hub_config.cloud_api_token},
            timeout=5  # Short timeout para no bloquear login
        )

        if response.status_code == 200:
            data = response.json()
            has_access = data.get('has_access', False)

            # Sincronizar estado local con Cloud
            if not has_access and user.is_active:
                user.is_active = False
                user.save(update_fields=['is_active'])
                return False, "removed_from_cloud"
            elif has_access and not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])
                return True, "reactivated_from_cloud"

            return has_access, "synced_with_cloud"
        else:
            # Cloud retornó error, confiar en estado local
            return user.is_active, "cloud_error_use_local"

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        # Sin conexión, confiar en estado local
        return user.is_active, "offline_use_local"
    except Exception as e:
        # Error inesperado, confiar en estado local pero loguear
        print(f"Error verificando acceso en Cloud: {str(e)}")
        return user.is_active, "error_use_local"


# Views

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
            # Verificar acceso con Cloud (sync on demand)
            has_access, reason = verify_user_access_with_cloud(user)

            if not has_access:
                return JsonResponse({
                    'success': False,
                    'error': 'Access denied. You have been removed from this Hub.',
                    'reason': reason
                })

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
                },
                'sync_reason': reason  # Informar al cliente cómo se sincronizó
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
        cloud_api_url = django_settings.CLOUD_API_URL

        try:
            response = requests.post(
                f"{cloud_api_url}/api/auth/login/",
                json={'email': email, 'password': password},
                timeout=10
            )

            if response.status_code == 200:
                auth_data = response.json()
                access_token = auth_data.get('access')
                refresh_token = auth_data.get('refresh')

                # Cache JWT tokens in database for offline validation
                token_cache = TokenCache.get_cache()
                token_cache.cache_jwt_tokens(access_token, refresh_token)
                print(f"[CLOUD LOGIN] ✓ JWT tokens cached for offline validation")

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
                            hub_config.cloud_api_token = hub_data.get('cloud_api_token')
                            hub_config.is_configured = True
                            hub_config.save()

                    # Get Hub config to use OS language as default
                    hub_config = HubConfig.get_config()

                    # Check if this is the first user in the Hub
                    is_first_user = LocalUser.objects.count() == 0

                    # Check if user already exists locally (by email or cloud_user_id)
                    cloud_user_id = user_info.get('id')

                    # Try to get existing user by cloud_user_id or email
                    local_user = None
                    created = False

                    try:
                        # First try by cloud_user_id
                        local_user = LocalUser.objects.get(cloud_user_id=cloud_user_id)
                    except LocalUser.DoesNotExist:
                        try:
                            # Then try by email
                            local_user = LocalUser.objects.get(email=email)
                            # Update cloud_user_id if it changed
                            local_user.cloud_user_id = cloud_user_id
                            local_user.save(update_fields=['cloud_user_id'])
                        except LocalUser.DoesNotExist:
                            # Create new user
                            local_user = LocalUser.objects.create(
                                cloud_user_id=cloud_user_id,
                                email=email,
                                name=user_info.get('name', email.split('@')[0]),
                                role='admin' if is_first_user else 'cashier',
                                pin_hash='',
                                language=user_info.get('language', hub_config.os_language),
                            )
                            created = True

                    # Si el usuario existía pero estaba inactivo, reactivarlo
                    if not created and not local_user.is_active:
                        local_user.is_active = True
                        local_user.pin_hash = ''  # Reset PIN para que configure uno nuevo
                        local_user.save(update_fields=['is_active', 'pin_hash'])
                        created = True  # Forzar flujo de primer login (configurar PIN)

                    # Register user on Hub in Cloud (creates HubUser relationship)
                    try:
                        import platform
                        register_url = f"{cloud_api_url}/api/hubs/{hub_config.hub_id}/users/register/"
                        register_payload = {
                            'user_email': email,
                            'metadata': {
                                'device': platform.system(),
                                'hub_version': '1.0.0',  # TODO: Get from config
                            }
                        }
                        register_headers = {'Authorization': f'Bearer {access_token}'}

                        print(f"[CLOUD LOGIN] Registering user on Hub in Cloud...")
                        print(f"[CLOUD LOGIN] URL: {register_url}")
                        print(f"[CLOUD LOGIN] Payload: {register_payload}")
                        print(f"[CLOUD LOGIN] Headers: Authorization: Bearer {access_token[:20]}...")

                        register_response = requests.post(
                            register_url,
                            json=register_payload,
                            headers=register_headers,
                            timeout=10
                        )

                        print(f"[CLOUD LOGIN] Registration response status: {register_response.status_code}")
                        print(f"[CLOUD LOGIN] Registration response: {register_response.text}")

                        if register_response.status_code not in [200, 201]:
                            # Log error but don't block login
                            print(f"[CLOUD LOGIN] Warning: Failed to register user on Cloud Hub")
                            print(f"[CLOUD LOGIN] Status: {register_response.status_code}")
                            print(f"[CLOUD LOGIN] Response: {register_response.text}")
                        else:
                            print(f"[CLOUD LOGIN] ✓ User successfully registered on Hub in Cloud")
                    except requests.exceptions.ConnectionError as e:
                        print(f"[CLOUD LOGIN] Warning: Could not connect to Cloud: {str(e)}")
                    except requests.exceptions.Timeout as e:
                        print(f"[CLOUD LOGIN] Warning: Cloud request timeout: {str(e)}")
                    except Exception as e:
                        # Log error but don't block login
                        print(f"[CLOUD LOGIN] Warning: Unexpected error registering user: {str(e)}")
                        import traceback
                        traceback.print_exc()

                    # Check if user has PIN configured
                    first_time = not local_user.pin_hash

                    # Store JWT token in session for middleware validation
                    request.session['jwt_token'] = access_token
                    request.session['jwt_refresh'] = refresh_token
                    request.session['local_user_id'] = local_user.id
                    request.session['user_name'] = local_user.name
                    request.session['user_email'] = local_user.email
                    request.session['user_role'] = local_user.role
                    request.session['user_language'] = local_user.language

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


def logout(request):
    """
    Logout - clear session
    """
    request.session.flush()
    return redirect('accounts:login')


def employees(request):
    """
    Employees management view
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

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

        # Soft delete locally
        user.is_active = False
        user.save()

        # No need to sync immediately - will sync on next login attempt
        # The user will be denied access when they try to login
        print(f"User {user.email} marked as inactive locally")

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

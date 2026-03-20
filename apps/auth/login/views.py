"""
Auth Login Views

Handles local PIN login and Cloud login authentication.
Supports trusted/untrusted device system for AWS deployment.
"""
import json
import logging
import os
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings as django_settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

from apps.accounts.models import LocalUser, TrustedDevice
from apps.configuration.models import HubConfig
from apps.sync.models import TokenCache


def _get_current_user(request):
    """Get LocalUser from session if authenticated."""
    user_id = request.session.get('local_user_id')
    if not user_id:
        return None
    try:
        return LocalUser.objects.get(id=user_id, is_active=True)
    except LocalUser.DoesNotExist:
        return None


def login(request):
    """
    Login page - supports both local PIN login and Cloud login.
    Extends base.html directly (no dashboard layout).

    Employee data is NOT sent on page load — it is fetched via AJAX
    only after device trust is verified or Cloud SSO completes.
    """
    context = {
        'local_users_json': '[]',
    }

    return render(request, 'auth/login/pages/index.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def get_employees(request):
    """
    Return employee list as JSON for the login page.

    Only returns data if the device is trusted (valid device_token)
    or the user has an active Cloud session (jwt_token in session).
    """
    try:
        data = json.loads(request.body)
        device_token = data.get('device_token')
    except (json.JSONDecodeError, TypeError):
        device_token = None

    has_cloud_session = bool(request.session.get('jwt_token'))

    # Verify device trust if token provided
    device_trusted = False
    trusted_user_ids = []
    if device_token:
        devices = TrustedDevice.objects.filter(
            device_token=device_token,
            is_revoked=False,
        ).select_related('user')
        valid_devices = [d for d in devices if d.is_valid() and d.user.is_active]
        if valid_devices:
            device_trusted = True
            trusted_user_ids = [str(d.user.id) for d in valid_devices]

    # Only return employees if authorized
    if not device_trusted and not has_cloud_session:
        return JsonResponse({'authorized': False, 'employees': []})

    local_users = LocalUser.objects.filter(is_active=True).order_by('name')
    employees = [
        {
            'id': str(user.id),
            'name': user.name,
            'initials': user.get_initials(),
            'role': user.role.capitalize(),
            'roleColor': user.get_role_color(),
        }
        for user in local_users
    ]

    return JsonResponse({
        'authorized': True,
        'employees': employees,
        'trusted_user_ids': trusted_user_ids,
    })


@csrf_exempt
@require_http_methods(["POST"])
def verify_device_trust(request):
    """
    Verify if a device token is valid.
    Returns the list of users trusted on this device.
    Called from login page on load if a device token exists in localStorage.
    """
    try:
        data = json.loads(request.body)
        device_token = data.get('device_token')

        if not device_token:
            return JsonResponse({'trusted': False})

        devices = TrustedDevice.objects.filter(
            device_token=device_token,
            is_revoked=False,
        ).select_related('user')

        # Filter to valid (non-expired) devices with active users
        valid_devices = [d for d in devices if d.is_valid() and d.user.is_active]

        if not valid_devices:
            return JsonResponse({'trusted': False})

        # Return IDs of trusted Cloud users (template merges with local employees)
        trusted_user_ids = [str(d.user.id) for d in valid_devices]

        return JsonResponse({
            'trusted': True,
            'trusted_user_ids': trusted_user_ids,
        })

    except Exception as e:
        logger.error(f"verify_device_trust error: {e}")
        return JsonResponse({'trusted': False})


@csrf_exempt
@require_http_methods(["POST"])
def verify_pin(request):
    """Verify PIN for local user login -- only on trusted devices for Cloud users."""
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        pin = data.get('pin')
        device_token = data.get('device_token')

        if not user_id or not pin:
            return JsonResponse({'success': False, 'error': 'Missing data'})

        try:
            user = LocalUser.objects.get(id=user_id, is_active=True)
        except LocalUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'})

        # Rate limiting: max 3 failed PIN attempts per user per 24 hours
        cache_key = f'pin_attempts_{user_id}'
        attempts = cache.get(cache_key, 0)

        if attempts >= 3:
            return JsonResponse({
                'success': False,
                'error': 'Too many attempts. Try again in 24 hours or use email login.',
                'locked': True,
            })

        # Verify device trust for Cloud users
        # Skip trust check if user just completed Cloud SSO (jwt_token in session)
        has_cloud_session = bool(request.session.get('jwt_token'))
        trusted_device = None

        if user.is_cloud_user and not has_cloud_session:
            if device_token:
                trusted_device = TrustedDevice.objects.filter(
                    device_token=device_token,
                    user=user,
                    is_revoked=False,
                ).first()

                if not trusted_device or not trusted_device.is_valid():
                    return JsonResponse({
                        'success': False,
                        'error': 'Device not trusted. Please log in with email and password.',
                        'device_untrusted': True,
                    })
            else:
                # Cloud user on untrusted device -- must use Cloud SSO
                return JsonResponse({
                    'success': False,
                    'error': 'Device not trusted. Please log in with email and password.',
                    'device_untrusted': True,
                })
        elif user.is_cloud_user and has_cloud_session and device_token:
            # Already authenticated via Cloud SSO, just refresh device trust if exists
            trusted_device = TrustedDevice.objects.filter(
                device_token=device_token,
                user=user,
                is_revoked=False,
            ).first()

        # Local-only employees (no cloud_user_id) can always use PIN
        # (they have no Cloud account to authenticate with)

        if user.check_pin(pin):
            # Clear rate limit on success
            cache.delete(cache_key)

            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])

            hub_config = HubConfig.get_config()
            request.session['local_user_id'] = str(user.id)
            request.session['hub_id'] = str(hub_config.hub_id)
            request.session['user_name'] = user.name
            request.session['user_email'] = user.email
            request.session['user_role'] = user.role
            request.session['user_language'] = user.language

            # Refresh device trust on successful PIN login
            if trusted_device:
                trusted_device.refresh()

            return JsonResponse({
                'success': True,
                'user': {
                    'id': str(user.id),
                    'name': user.name,
                    'email': user.email,
                },
            })
        else:
            # Increment failed attempts
            cache.set(cache_key, attempts + 1, timeout=86400)  # 24 hours
            return JsonResponse({'success': False, 'error': 'Incorrect PIN'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def cloud_login(request):
    """Cloud login - authenticates against Cloud API"""
    try:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return JsonResponse({'success': False, 'error': 'Missing credentials'})

        cloud_api_url = django_settings.CLOUD_API_URL

        try:
            # Send X-Client-Type header so Cloud registers Hub and returns hub_jwt
            # In web mode, Hub already has credentials from env — don't re-register
            deployment_mode = getattr(django_settings, 'DEPLOYMENT_MODE', 'local')
            headers = {}
            if deployment_mode != 'web':
                headers['X-Client-Type'] = f'hub-{deployment_mode or "desktop"}'
            response = requests.post(
                f"{cloud_api_url}/api/auth/login/",
                json={'email': email, 'password': password},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                auth_data = response.json()
                access_token = auth_data.get('access')
                refresh_token = auth_data.get('refresh')

                # Save hub_jwt if Cloud returned it (Hub registration)
                hub_jwt = auth_data.get('hub_jwt')
                hub_refresh_token = auth_data.get('hub_refresh_token')
                hub_id = auth_data.get('hub_id')
                public_key = auth_data.get('public_key')

                if hub_jwt and hub_id:
                    hub_config = HubConfig.get_config()
                    update_fields = ['hub_jwt']
                    # Only set hub_id from Cloud if HUB_ID env is not set
                    # (env var is authoritative in web deployment mode)
                    if not os.environ.get('HUB_ID'):
                        hub_config.hub_id = hub_id
                        update_fields.append('hub_id')
                    hub_config.hub_jwt = hub_jwt
                    if hub_refresh_token:
                        hub_config.hub_refresh_token = hub_refresh_token
                        update_fields.append('hub_refresh_token')
                    if public_key:
                        hub_config.cloud_public_key = public_key
                        update_fields.append('cloud_public_key')
                    hub_config.save(update_fields=update_fields)

                    # Ensure roles and permissions exist with correct hub_id
                    try:
                        from apps.core.services.permission_service import PermissionService
                        PermissionService.create_default_roles(str(hub_id))
                        PermissionService.sync_all_module_permissions(str(hub_id))
                    except Exception as e:
                        logger.warning(f"Failed to sync roles/permissions: {e}")

                    # Start WebSocket client for heartbeat now that we have hub_jwt
                    try:
                        from apps.sync.services.websocket_client import start_websocket_client
                        start_websocket_client()
                    except Exception as e:
                        logger.warning(f"Failed to start WebSocket client: {e}")

                token_cache = TokenCache.get_cache()
                token_cache.cache_jwt_tokens(access_token, refresh_token)

                user_response = requests.get(
                    f"{cloud_api_url}/api/auth/me/",
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10
                )

                if user_response.status_code == 200:
                    user_info = user_response.json()
                    hub_config = HubConfig.get_config()
                    cloud_user_id = user_info.get('id')

                    local_user = None
                    created = False

                    try:
                        local_user = LocalUser.objects.get(cloud_user_id=cloud_user_id)
                    except LocalUser.DoesNotExist:
                        try:
                            local_user = LocalUser.objects.get(email=email)
                            local_user.cloud_user_id = cloud_user_id
                            local_user.save(update_fields=['cloud_user_id'])
                        except LocalUser.DoesNotExist:
                            local_user = LocalUser.objects.create(
                                cloud_user_id=cloud_user_id,
                                email=email,
                                name=user_info.get('name', email.split('@')[0]),
                                role='admin',
                                pin_hash='',
                                language=user_info.get('language', hub_config.os_language),
                            )
                            created = True

                    if not created and not local_user.is_active:
                        local_user.is_active = True
                        local_user.pin_hash = ''
                        local_user.save(update_fields=['is_active', 'pin_hash'])
                        created = True

                    # Register user on Hub in Cloud
                    try:
                        import platform
                        register_response = requests.post(
                            f"{cloud_api_url}/api/hubs/{hub_config.hub_id}/users/register/",
                            json={
                                'user_email': email,
                                'metadata': {
                                    'device': platform.system(),
                                    'hub_version': '1.0.0',
                                }
                            },
                            headers={'Authorization': f'Bearer {access_token}'},
                            timeout=10
                        )
                    except Exception as e:
                        print(f"[CLOUD LOGIN] Warning: {str(e)}")

                    first_time = not local_user.pin_hash

                    # Store Cloud session (JWT) -- persists across browser sessions
                    request.session['jwt_token'] = access_token
                    request.session['jwt_refresh'] = refresh_token

                    # Store pending user for trust_device validation
                    request.session['pending_user_id'] = str(local_user.id)
                    request.session['pending_user_email'] = local_user.email

                    # Don't set local_user_id here -- user must select
                    # profile + enter PIN on the login screen
                    return JsonResponse({
                        'success': True,
                        'first_time': first_time,
                        'user': {
                            'id': str(local_user.id),
                            'name': local_user.name,
                            'email': local_user.email,
                        },
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
def trust_device(request):
    """Register current device as trusted for the authenticated user."""
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')

        if not user_id:
            return JsonResponse({'success': False, 'error': 'Missing user_id'})

        # Must have an active Cloud session (JWT in session = just did Cloud SSO)
        if not request.session.get('jwt_token'):
            return JsonResponse({'success': False, 'error': 'Cloud session required'})

        # Validate that user_id matches the user who just completed Cloud SSO
        # (pending_user_id is set during cloud_login, or local_user_id after PIN setup)
        session_user_id = (
            request.session.get('pending_user_id')
            or request.session.get('local_user_id')
        )
        if str(user_id) != str(session_user_id):
            return JsonResponse({'success': False, 'error': 'User mismatch'})

        try:
            user = LocalUser.objects.get(id=user_id, is_active=True)
        except LocalUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'})

        hub_config = HubConfig.get_config()
        device = TrustedDevice.create_for_user(
            user=user,
            request=request,
            hub_id=str(hub_config.hub_id),
        )

        return JsonResponse({
            'success': True,
            'device_token': device.device_token,
        })

    except Exception as e:
        logger.error(f"trust_device error: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["POST"])
def revoke_device(request):
    """Revoke trust for a specific device."""
    try:
        data = json.loads(request.body)
        device_id = data.get('device_id')

        user = _get_current_user(request)
        if not user:
            return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

        try:
            device = TrustedDevice.objects.get(id=device_id)
        except TrustedDevice.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Device not found'})

        # Users can revoke their own devices; admins can revoke anyone's
        if str(device.user_id) != str(user.id) and user.get_role_name() != 'admin':
            return JsonResponse({'success': False, 'error': 'Permission denied'})

        device.revoke()
        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
def setup_pin(request):
    """Setup PIN for first-time Cloud login user (SSO flow)"""
    if request.method == 'GET':
        pending_user_id = request.session.get('pending_user_id')
        logger.info(f"[SETUP-PIN] GET request, pending_user_id={pending_user_id}")

        if not pending_user_id:
            logger.info("[SETUP-PIN] No pending_user_id in session, redirecting to login")
            return redirect('auth:login')

        try:
            user = LocalUser.objects.get(id=pending_user_id)
        except LocalUser.DoesNotExist:
            logger.warning(f"[SETUP-PIN] User {pending_user_id} not found, redirecting to login")
            return redirect('auth:login')

        pending_user_data = {
            'id': str(user.id),
            'name': user.name,
            'email': user.email,
        }
        context = {
            'show_pin_setup': True,
            'pending_user': json.dumps(pending_user_data),
            'local_users_json': '[]',
        }
        return render(request, 'auth/login/pages/index.html', context)

    # POST: Save PIN
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        pin = data.get('pin')

        if not user_id:
            user_id = request.session.get('pending_user_id')

        logger.info(f"[SETUP-PIN] POST request, user_id={user_id}")

        if not user_id or not pin:
            return JsonResponse({'success': False, 'error': 'Missing data'})

        if len(pin) != 4 or not pin.isdigit():
            return JsonResponse({'success': False, 'error': 'PIN must be 4 digits'})

        try:
            user = LocalUser.objects.get(id=user_id)
        except LocalUser.DoesNotExist:
            logger.warning(f"[SETUP-PIN] User {user_id} not found")
            return JsonResponse({'success': False, 'error': 'User not found'})

        user.set_pin(pin)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        if 'pending_user_id' in request.session:
            del request.session['pending_user_id']
        if 'pending_user_email' in request.session:
            del request.session['pending_user_email']

        hub_config = HubConfig.get_config()
        request.session['local_user_id'] = str(user.id)
        request.session['hub_id'] = str(hub_config.hub_id)
        request.session['user_name'] = user.name
        request.session['user_email'] = user.email
        request.session['user_role'] = user.role
        request.session['user_language'] = user.language

        logger.info(f"[SETUP-PIN] PIN configured for {user.email}, session established")
        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"[SETUP-PIN] Error: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


def logout(request):
    """Logout - auto-close cash session if configured, then clear session."""
    hub_id = request.session.get('hub_id')
    local_user_id = request.session.get('local_user_id')

    if hub_id and local_user_id:
        try:
            from cash_register.models import CashRegisterSettings, CashSession
            config = CashRegisterSettings.get_settings(hub_id)
            if config.enable_cash_register and config.auto_close_session_on_logout:
                user = LocalUser.objects.get(pk=local_user_id)
                open_session = CashSession.get_current_session(hub_id, user)
                if open_session:
                    closing_balance = open_session.get_current_balance()
                    open_session.close_session(closing_balance, notes='Auto-closed on logout')
        except Exception:
            pass

    # Clear PIN session but preserve Cloud session (JWT tokens)
    # so user doesn't have to re-enter Cloud credentials
    for key in ['local_user_id', 'hub_id', 'user_name', 'user_email', 'user_role', 'user_language']:
        request.session.pop(key, None)
    return redirect('auth:login')

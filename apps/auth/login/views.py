"""
Auth Login Views

Handles local PIN login and Cloud login authentication.
"""
import json
import logging
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings as django_settings

logger = logging.getLogger(__name__)

from apps.accounts.models import LocalUser
from apps.configuration.models import HubConfig
from apps.sync.models import TokenCache


def verify_user_access_with_cloud(user):
    """
    Verify if user has active access to Hub by querying Cloud.

    Runs during login to sync user state.
    If Hub is offline, trust local state.
    """
    hub_config = HubConfig.get_config()

    if not hub_config.is_configured:
        return True, "hub_not_configured"

    try:
        response = requests.get(
            f"{django_settings.CLOUD_API_URL}/api/hubs/{hub_config.hub_id}/users/check/{user.email}/",
            headers={'X-Hub-Token': hub_config.cloud_api_token},
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            has_access = data.get('has_access', False)

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
            return user.is_active, "cloud_error_use_local"

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return user.is_active, "offline_use_local"
    except Exception as e:
        print(f"Error verifying access in Cloud: {str(e)}")
        return user.is_active, "error_use_local"


def login(request):
    """
    Login page - supports both local PIN login and Cloud login.
    Extends base.html directly (no dashboard layout).
    """
    local_users = LocalUser.objects.filter(is_active=True).order_by('name')

    local_users_data = [
        {
            'id': str(user.id),
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

    return render(request, 'auth/login/pages/index.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def verify_pin(request):
    """Verify PIN for local user login"""
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        pin = data.get('pin')

        if not user_id or not pin:
            return JsonResponse({'success': False, 'error': 'Missing data'})

        try:
            user = LocalUser.objects.get(id=user_id, is_active=True)
        except LocalUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'})

        if user.check_pin(pin):
            has_access, reason = verify_user_access_with_cloud(user)

            if not has_access:
                return JsonResponse({
                    'success': False,
                    'error': 'Access denied. You have been removed from this Hub.',
                    'reason': reason
                })

            user.last_login = timezone.now()
            user.save()

            request.session['local_user_id'] = str(user.id)
            request.session['hub_id'] = str(user.hub_id)
            request.session['user_name'] = user.name
            request.session['user_email'] = user.email
            request.session['user_role'] = user.role
            request.session['user_language'] = user.language

            return JsonResponse({
                'success': True,
                'user': {
                    'id': str(user.id),
                    'name': user.name,
                    'email': user.email,
                },
                'sync_reason': reason
            })
        else:
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
            response = requests.post(
                f"{cloud_api_url}/api/auth/login/",
                json={'email': email, 'password': password},
                headers={'X-Client-Type': 'hub-desktop'},
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
                    hub_config.hub_id = hub_id
                    hub_config.hub_jwt = hub_jwt
                    if hub_refresh_token:
                        hub_config.hub_refresh_token = hub_refresh_token
                    if public_key:
                        hub_config.cloud_public_key = public_key
                    hub_config.is_configured = True
                    hub_config.save()

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
                    is_first_user = LocalUser.objects.count() == 0
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
                                role='admin' if is_first_user else 'cashier',
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

                    request.session['jwt_token'] = access_token
                    request.session['jwt_refresh'] = refresh_token
                    request.session['local_user_id'] = str(local_user.id)
                    request.session['hub_id'] = str(local_user.hub_id)
                    request.session['user_name'] = local_user.name
                    request.session['user_email'] = local_user.email
                    request.session['user_role'] = local_user.role
                    request.session['user_language'] = local_user.language

                    return JsonResponse({
                        'success': True,
                        'first_time': first_time,
                        'user': {
                            'id': str(local_user.id),
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
def setup_pin(request):
    """Setup PIN for first-time Cloud login user"""
    if request.method == 'GET':
        pending_user_id = request.session.get('pending_user_id')

        if not pending_user_id:
            return redirect('auth:login')

        try:
            user = LocalUser.objects.get(id=pending_user_id)
        except LocalUser.DoesNotExist:
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

        if not user_id or not pin:
            return JsonResponse({'success': False, 'error': 'Missing data'})

        if len(pin) != 4 or not pin.isdigit():
            return JsonResponse({'success': False, 'error': 'PIN must be 4 digits'})

        try:
            user = LocalUser.objects.get(id=user_id)
        except LocalUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'})

        user.set_pin(pin)
        user.last_login = timezone.now()
        user.save()

        if 'pending_user_id' in request.session:
            del request.session['pending_user_id']
        if 'pending_user_email' in request.session:
            del request.session['pending_user_email']

        request.session['local_user_id'] = str(user.id)
        request.session['hub_id'] = str(user.hub_id)
        request.session['user_name'] = user.name
        request.session['user_email'] = user.email
        request.session['user_role'] = user.role
        request.session['user_language'] = user.language

        return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def logout(request):
    """Logout - clear session"""
    request.session.flush()
    return redirect('auth:login')

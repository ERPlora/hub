import json
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from .models import HubConfig, LocalUser


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

    return render(request, 'core/dashboard.html')


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

    return render(request, 'core/pos.html')


def settings(request):
    """
    Settings view
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('core:login')

    hub_config = HubConfig.get_config()
    context = {
        'hub_config': hub_config
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
        'local_users': local_users
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

"""
Main Employees Views

Employee management: list, create, update, delete, reset PIN.
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.accounts.models import LocalUser


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/content.html')
def index(request):
    """Employees management page"""
    local_users = LocalUser.objects.filter(is_active=True).order_by('name')

    return {
        'current_section': 'employees',
        'page_title': 'Employees',
        'local_users': local_users,
    }


# ============================================================================
# Employee API Endpoints
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_create(request):
    """API: Create new employee"""
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
def api_update(request):
    """API: Update employee"""
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
def api_delete(request):
    """API: Delete employee (soft delete)"""
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

        return JsonResponse({'success': True})

    except LocalUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_reset_pin(request):
    """API: Reset employee PIN"""
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

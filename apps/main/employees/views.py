"""
Main Employees Views

Employee management: list, create, update, delete, reset PIN.
"""
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render as django_render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.accounts.models import LocalUser


# Role options for select component
ROLE_OPTIONS = [
    {'value': 'admin', 'label': _('Admin')},
    {'value': 'manager', 'label': _('Manager')},
    {'value': 'employee', 'label': _('Employee')},
]


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/content.html')
def index(request):
    """Employees management page"""
    from django.db.models import Q

    search_query = request.GET.get('q', '').strip()
    local_users = LocalUser.objects.filter(is_active=True)

    if search_query:
        local_users = local_users.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(role__icontains=search_query)
        )

    local_users = local_users.order_by('name')

    # If HTMX request targeting the list, return only the list partial
    if request.htmx and request.htmx.target == 'employees-list':
        return django_render(request, 'main/employees/partials/employees_list.html', {
            'local_users': local_users,
            'search_query': search_query,
        })

    return {
        'current_section': 'employees',
        'page_title': 'Employees',
        'local_users': local_users,
        'search_query': search_query,
    }


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/add.html')
def add(request):
    """Add employee page (GET) or create employee (POST)"""
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        role = request.POST.get('role', 'employee')
        pin = request.POST.get('pin')

        if not name or not email or not pin:
            messages.error(request, 'Please fill all required fields')
            return {
                'current_section': 'employees',
                'page_title': 'Add Employee',
                'role_options': ROLE_OPTIONS,
            }

        if len(pin) != 4 or not pin.isdigit():
            messages.error(request, 'PIN must be 4 digits')
            return {
                'current_section': 'employees',
                'page_title': 'Add Employee',
                'role_options': ROLE_OPTIONS,
            }

        if LocalUser.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return {
                'current_section': 'employees',
                'page_title': 'Add Employee',
                'role_options': ROLE_OPTIONS,
            }

        # Create local-only employee
        user = LocalUser.objects.create(
            cloud_user_id=None,
            email=email,
            name=name,
            role=role
        )
        user.set_pin(pin)
        user.save()

        messages.success(request, 'Employee added successfully')
        # Return the list content
        local_users = LocalUser.objects.filter(is_active=True).order_by('name')
        return {
            'current_section': 'employees',
            'page_title': 'Employees',
            'local_users': local_users,
            'template': 'main/employees/partials/content.html',
        }

    return {
        'current_section': 'employees',
        'page_title': 'Add Employee',
        'role_options': ROLE_OPTIONS,
    }


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/edit.html')
def edit(request, employee_id):
    """Edit employee page (GET) or update employee (POST)"""
    employee = get_object_or_404(LocalUser, id=employee_id, is_active=True)

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        role = request.POST.get('role')

        if not name or not email or not role:
            messages.error(request, 'Please fill all required fields')
            return {
                'current_section': 'employees',
                'page_title': 'Edit Employee',
                'employee': employee,
                'role_options': ROLE_OPTIONS,
                'employee_delete_url': reverse('main:employee_delete', args=[employee.id]),
                'employees_url': reverse('main:employees'),
            }

        # Check if email changed and is already in use
        if employee.email != email and LocalUser.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return {
                'current_section': 'employees',
                'page_title': 'Edit Employee',
                'employee': employee,
                'role_options': ROLE_OPTIONS,
                'employee_delete_url': reverse('main:employee_delete', args=[employee.id]),
                'employees_url': reverse('main:employees'),
            }

        employee.name = name
        employee.email = email
        employee.role = role
        employee.save()

        messages.success(request, 'Employee updated successfully')
        # Return the list content
        local_users = LocalUser.objects.filter(is_active=True).order_by('name')
        return {
            'current_section': 'employees',
            'page_title': 'Employees',
            'local_users': local_users,
            'template': 'main/employees/partials/content.html',
        }

    return {
        'current_section': 'employees',
        'page_title': 'Edit Employee',
        'employee': employee,
        'role_options': ROLE_OPTIONS,
        'employee_delete_url': reverse('main:employee_delete', args=[employee.id]),
        'employees_url': reverse('main:employees'),
    }


@login_required
@require_POST
def reset_pin(request, employee_id):
    """Reset employee PIN"""
    employee = get_object_or_404(LocalUser, id=employee_id, is_active=True)
    pin = request.POST.get('pin')

    if not pin or len(pin) != 4 or not pin.isdigit():
        return HttpResponse(status=400)

    employee.set_pin(pin)
    employee.save()

    return django_render(
        request,
        'main/employees/partials/pin_reset_success.html',
        {'employee': employee}
    )


@login_required
@require_POST
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/content.html')
def delete(request, employee_id):
    """Delete (deactivate) employee"""
    employee = get_object_or_404(LocalUser, id=employee_id, is_active=True)

    # Prevent deleting admin users
    if employee.role == 'admin':
        messages.error(request, 'Cannot delete admin users')
        return {
            'current_section': 'employees',
            'page_title': 'Employees',
            'local_users': LocalUser.objects.filter(is_active=True).order_by('name'),
        }

    # Soft delete
    employee.is_active = False
    employee.save()

    messages.success(request, 'Employee deleted successfully')
    return {
        'current_section': 'employees',
        'page_title': 'Employees',
        'local_users': LocalUser.objects.filter(is_active=True).order_by('name'),
    }

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
from apps.accounts.models import LocalUser, Role


def get_role_options(hub_id):
    """Get role options from database for select component."""
    roles = Role.objects.filter(hub_id=hub_id, is_active=True, is_deleted=False).order_by('name')
    return [{'value': str(role.id), 'label': role.display_name} for role in roles]


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/content.html')
def index(request):
    """Employees management page"""
    from django.db.models import Q

    hub_id = request.session.get('hub_id')
    search_query = request.GET.get('q', '').strip()
    local_users = LocalUser.objects.filter(hub_id=hub_id, is_active=True)

    if search_query:
        local_users = local_users.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(role_obj__name__icontains=search_query) |
            Q(role_obj__display_name__icontains=search_query)
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
    hub_id = request.session.get('hub_id')
    role_options = get_role_options(hub_id)

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        role_id = request.POST.get('role_id')
        pin = request.POST.get('pin')

        if not name or not email or not pin:
            messages.error(request, _('Please fill all required fields'))
            return {
                'current_section': 'employees',
                'page_title': _('Add Employee'),
                'role_options': role_options,
            }

        if len(pin) != 4 or not pin.isdigit():
            messages.error(request, _('PIN must be 4 digits'))
            return {
                'current_section': 'employees',
                'page_title': _('Add Employee'),
                'role_options': role_options,
            }

        if LocalUser.objects.filter(hub_id=hub_id, email=email).exists():
            messages.error(request, _('Email already exists'))
            return {
                'current_section': 'employees',
                'page_title': _('Add Employee'),
                'role_options': role_options,
            }

        # Get role object (default to employee if not found)
        role_obj = None
        if role_id:
            role_obj = Role.objects.filter(id=role_id, hub_id=hub_id, is_active=True).first()
        if not role_obj:
            role_obj = Role.objects.filter(hub_id=hub_id, name='employee', is_active=True).first()

        # Create local-only employee
        user = LocalUser.objects.create(
            hub_id=hub_id,
            cloud_user_id=None,
            email=email,
            name=name,
            role_obj=role_obj,
            role=role_obj.name if role_obj else 'employee',  # Keep legacy field in sync
        )
        user.set_pin(pin)
        user.save()

        messages.success(request, _('Employee added successfully'))
        # Return the list content
        local_users = LocalUser.objects.filter(hub_id=hub_id, is_active=True).order_by('name')
        return {
            'current_section': 'employees',
            'page_title': _('Employees'),
            'local_users': local_users,
            'template': 'main/employees/partials/content.html',
        }

    return {
        'current_section': 'employees',
        'page_title': _('Add Employee'),
        'role_options': role_options,
    }


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/edit.html')
def edit(request, employee_id):
    """Edit employee page (GET) or update employee (POST)"""
    hub_id = request.session.get('hub_id')
    employee = get_object_or_404(LocalUser, id=employee_id, hub_id=hub_id, is_active=True)
    role_options = get_role_options(hub_id)

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        role_id = request.POST.get('role_id')

        if not name or not email:
            messages.error(request, _('Please fill all required fields'))
            return {
                'current_section': 'employees',
                'page_title': _('Edit Employee'),
                'employee': employee,
                'role_options': role_options,
                'employee_delete_url': reverse('main:employee_delete', args=[employee.id]),
                'employees_url': reverse('main:employees'),
            }

        # Check if email changed and is already in use
        if employee.email != email and LocalUser.objects.filter(hub_id=hub_id, email=email).exists():
            messages.error(request, _('Email already exists'))
            return {
                'current_section': 'employees',
                'page_title': _('Edit Employee'),
                'employee': employee,
                'role_options': role_options,
                'employee_delete_url': reverse('main:employee_delete', args=[employee.id]),
                'employees_url': reverse('main:employees'),
            }

        # Get role object
        role_obj = None
        if role_id:
            role_obj = Role.objects.filter(id=role_id, hub_id=hub_id, is_active=True).first()

        employee.name = name
        employee.email = email
        if role_obj:
            employee.role_obj = role_obj
            employee.role = role_obj.name  # Keep legacy field in sync
        employee.save()

        messages.success(request, _('Employee updated successfully'))
        # Return the list content
        local_users = LocalUser.objects.filter(hub_id=hub_id, is_active=True).order_by('name')
        return {
            'current_section': 'employees',
            'page_title': _('Employees'),
            'local_users': local_users,
            'template': 'main/employees/partials/content.html',
        }

    return {
        'current_section': 'employees',
        'page_title': _('Edit Employee'),
        'employee': employee,
        'role_options': role_options,
        'employee_delete_url': reverse('main:employee_delete', args=[employee.id]),
        'employees_url': reverse('main:employees'),
    }


@login_required
@require_POST
def reset_pin(request, employee_id):
    """Reset employee PIN"""
    hub_id = request.session.get('hub_id')
    employee = get_object_or_404(LocalUser, id=employee_id, hub_id=hub_id, is_active=True)
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
    hub_id = request.session.get('hub_id')
    employee = get_object_or_404(LocalUser, id=employee_id, hub_id=hub_id, is_active=True)

    # Prevent deleting admin users
    if employee.get_role_name() == 'admin':
        messages.error(request, _('Cannot delete admin users'))
        return {
            'current_section': 'employees',
            'page_title': _('Employees'),
            'local_users': LocalUser.objects.filter(hub_id=hub_id, is_active=True).order_by('name'),
        }

    # Soft delete
    employee.is_active = False
    employee.save()

    messages.success(request, _('Employee deleted successfully'))
    return {
        'current_section': 'employees',
        'page_title': _('Employees'),
        'local_users': LocalUser.objects.filter(hub_id=hub_id, is_active=True).order_by('name'),
    }

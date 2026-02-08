"""
Main Employees Views

Employee management: list, create, update, delete, toggle status, bulk actions.
"""
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render as django_render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from apps.core.htmx import htmx_view
from apps.core.services import export_to_csv, export_to_excel
from apps.core.services.import_service import parse_import_file, ImportResult
from apps.accounts.decorators import login_required
from apps.accounts.models import LocalUser, Role

SORT_FIELDS = {
    'name': 'name',
    'email': 'email',
    'role': 'role_obj__display_name',
}

PER_PAGE_CHOICES = [10, 25, 50, 100]


def get_role_options(hub_id):
    """Get role options from database for select component."""
    roles = Role.objects.filter(hub_id=hub_id, is_active=True, is_deleted=False).order_by('name')
    return [{'value': str(role.id), 'label': role.display_name} for role in roles]


def _build_list_context(hub_id, per_page=10):
    """Build context dict for the employees list (used after mutations)."""
    local_users = LocalUser.objects.filter(hub_id=hub_id).order_by('name')
    active_count = local_users.filter(is_active=True).count()
    paginator = Paginator(local_users, per_page)
    page_obj = paginator.get_page(1)
    roles_list = Role.objects.filter(
        hub_id=hub_id, is_active=True, is_deleted=False
    ).order_by('display_name')
    return {
        'local_users': page_obj,
        'page_obj': page_obj,
        'search_query': '',
        'sort_field': 'name',
        'sort_dir': 'asc',
        'role_filter': '',
        'status_filter': '',
        'roles_list': roles_list,
        'current_view': 'table',
        'per_page': per_page,
        'active_count': active_count,
    }


def _render_list(request, hub_id, per_page=10):
    """Render the employees list partial after a mutation."""
    context = _build_list_context(hub_id, per_page)
    return django_render(request, 'main/employees/partials/employees_list.html', context)


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/content.html')
def index(request):
    """Employees management page with search, sort, filter, status and pagination."""
    hub_id = request.session.get('hub_id')
    search_query = request.GET.get('q', '').strip()
    sort_field = request.GET.get('sort', 'name')
    sort_dir = request.GET.get('dir', 'asc')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    page_number = request.GET.get('page', 1)
    current_view = request.GET.get('view', 'table')
    per_page = int(request.GET.get('per_page', 10))
    if per_page not in PER_PAGE_CHOICES:
        per_page = 10

    # Base queryset — show all employees (active + inactive) unless filtered
    local_users = LocalUser.objects.filter(hub_id=hub_id)

    # Status filter
    if status_filter == 'active':
        local_users = local_users.filter(is_active=True)
    elif status_filter == 'inactive':
        local_users = local_users.filter(is_active=False)

    if search_query:
        local_users = local_users.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(role_obj__name__icontains=search_query) |
            Q(role_obj__display_name__icontains=search_query)
        )

    if role_filter:
        local_users = local_users.filter(role_obj__id=role_filter)

    order_by = SORT_FIELDS.get(sort_field, 'name')
    if sort_dir == 'desc':
        order_by = f'-{order_by}'
    local_users = local_users.order_by(order_by)

    # Export (before pagination — exports all filtered results)
    export_format = request.GET.get('export')
    if export_format in ('csv', 'excel'):
        export_fields = ['name', 'email', 'get_role_display', 'is_active']
        export_headers = [str(_('Name')), str(_('Email')), str(_('Role')), str(_('Status'))]
        export_formatters = {
            'is_active': lambda v: str(_('Active')) if v else str(_('Inactive')),
        }
        if export_format == 'csv':
            return export_to_csv(
                local_users,
                fields=export_fields,
                headers=export_headers,
                field_formatters=export_formatters,
                filename='employees.csv',
            )
        return export_to_excel(
            local_users,
            fields=export_fields,
            headers=export_headers,
            field_formatters=export_formatters,
            filename='employees.xlsx',
            sheet_name=str(_('Employees')),
        )

    paginator = Paginator(local_users, per_page)
    page_obj = paginator.get_page(page_number)

    roles_list = Role.objects.filter(
        hub_id=hub_id, is_active=True, is_deleted=False
    ).order_by('display_name')

    active_count = LocalUser.objects.filter(hub_id=hub_id, is_active=True).count()

    context = {
        'local_users': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'roles_list': roles_list,
        'current_view': current_view,
        'per_page': per_page,
        'active_count': active_count,
    }

    # HTMX partial: swap only datatable body (search, sort, filter, paginate)
    if request.htmx and request.htmx.target == 'datatable-body':
        return django_render(request, 'main/employees/partials/employees_list.html', context)

    context.update({
        'current_section': 'employees',
        'page_title': 'Employees',
    })
    return context


@login_required
def add(request):
    """Add employee — renders in side panel via HTMX."""
    hub_id = request.session.get('hub_id')
    role_options = get_role_options(hub_id)

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        role_id = request.POST.get('role_id')
        pin = request.POST.get('pin')

        if not name or not email or not pin:
            messages.error(request, _('Please fill all required fields'))
            return django_render(request, 'main/employees/partials/panel_add.html', {
                'role_options': role_options,
            })

        if len(pin) != 4 or not pin.isdigit():
            messages.error(request, _('PIN must be 4 digits'))
            return django_render(request, 'main/employees/partials/panel_add.html', {
                'role_options': role_options,
            })

        if LocalUser.objects.filter(hub_id=hub_id, email=email).exists():
            messages.error(request, _('Email already exists'))
            return django_render(request, 'main/employees/partials/panel_add.html', {
                'role_options': role_options,
            })

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
            role=role_obj.name if role_obj else 'employee',
        )
        user.set_pin(pin)
        user.save()

        messages.success(request, _('Employee added successfully'))
        return _render_list(request, hub_id)

    # GET: render panel form
    return django_render(request, 'main/employees/partials/panel_add.html', {
        'role_options': role_options,
    })


@login_required
def edit(request, employee_id):
    """Edit employee — renders in side panel via HTMX."""
    hub_id = request.session.get('hub_id')
    employee = get_object_or_404(LocalUser, id=employee_id, hub_id=hub_id)
    role_options = get_role_options(hub_id)

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        role_id = request.POST.get('role_id')

        if not name or not email:
            messages.error(request, _('Please fill all required fields'))
            return django_render(request, 'main/employees/partials/panel_edit.html', {
                'employee': employee,
                'role_options': role_options,
            })

        # Check if email changed and is already in use
        if employee.email != email and LocalUser.objects.filter(hub_id=hub_id, email=email).exists():
            messages.error(request, _('Email already exists'))
            return django_render(request, 'main/employees/partials/panel_edit.html', {
                'employee': employee,
                'role_options': role_options,
            })

        # Get role object
        role_obj = None
        if role_id:
            role_obj = Role.objects.filter(id=role_id, hub_id=hub_id, is_active=True).first()

        employee.name = name
        employee.email = email
        if role_obj:
            employee.role_obj = role_obj
            employee.role = role_obj.name
        employee.save()

        messages.success(request, _('Employee updated successfully'))
        return _render_list(request, hub_id)

    # GET: render panel form
    return django_render(request, 'main/employees/partials/panel_edit.html', {
        'employee': employee,
        'role_options': role_options,
    })


@login_required
@require_POST
def toggle_status(request, employee_id):
    """Toggle employee active/inactive status."""
    hub_id = request.session.get('hub_id')
    employee = get_object_or_404(LocalUser, id=employee_id, hub_id=hub_id)

    # Prevent deactivating admin users
    if employee.get_role_name() == 'admin' and employee.is_active:
        messages.error(request, _('Cannot deactivate admin users'))
        return _render_list(request, hub_id)

    # Prevent deactivating the last active user
    if employee.is_active:
        active_count = LocalUser.objects.filter(hub_id=hub_id, is_active=True).count()
        if active_count <= 1:
            messages.error(request, _('Cannot deactivate the last active employee'))
            return _render_list(request, hub_id)

    employee.is_active = not employee.is_active
    employee.save()

    status = _('activated') if employee.is_active else _('deactivated')
    messages.success(request, _('Employee %(status)s successfully') % {'status': status})
    return _render_list(request, hub_id)


@login_required
@require_POST
def bulk_toggle(request):
    """Bulk activate/deactivate/delete employees."""
    hub_id = request.session.get('hub_id')
    ids_str = request.POST.get('ids', '')
    action = request.POST.get('action', '')

    if not ids_str or not action:
        return _render_list(request, hub_id)

    ids = [uid.strip() for uid in ids_str.split(',') if uid.strip()]
    employees = LocalUser.objects.filter(hub_id=hub_id, id__in=ids)

    # Exclude admins from destructive actions
    if action in ('deactivate', 'delete'):
        admin_count = employees.filter(role_obj__name='admin').count()
        employees = employees.exclude(role_obj__name='admin')
        if admin_count:
            messages.warning(request, _('Admin users were excluded from this action'))

    count = employees.count()

    if action == 'activate':
        employees.update(is_active=True)
        messages.success(request, _('%(count)d employees activated') % {'count': count})
    elif action == 'deactivate':
        employees.update(is_active=False)
        messages.success(request, _('%(count)d employees deactivated') % {'count': count})
    elif action == 'delete':
        employees.update(is_active=False)
        messages.success(request, _('%(count)d employees deleted') % {'count': count})

    return _render_list(request, hub_id)


@login_required
@require_POST
def reset_pin(request, employee_id):
    """Reset employee PIN."""
    hub_id = request.session.get('hub_id')
    employee = get_object_or_404(LocalUser, id=employee_id, hub_id=hub_id)
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
def delete(request, employee_id):
    """Delete (deactivate) employee."""
    hub_id = request.session.get('hub_id')
    employee = get_object_or_404(LocalUser, id=employee_id, hub_id=hub_id)

    # Prevent deleting admin users
    if employee.get_role_name() == 'admin':
        messages.error(request, _('Cannot delete admin users'))
        return _render_list(request, hub_id)

    # Soft delete
    employee.is_active = False
    employee.save()

    messages.success(request, _('Employee deleted successfully'))
    return _render_list(request, hub_id)


@login_required
@require_POST
def import_employees(request):
    """Import employees from CSV or Excel file."""
    hub_id = request.session.get('hub_id')
    file = request.FILES.get('file')

    if not file:
        messages.error(request, _('Please select a file'))
        return _render_list(request, hub_id)

    try:
        rows = parse_import_file(file)
    except (ValueError, ImportError) as e:
        messages.error(request, str(e))
        return _render_list(request, hub_id)

    if not rows:
        messages.warning(request, _('The file is empty'))
        return _render_list(request, hub_id)

    result = ImportResult()
    for row_num, row in enumerate(rows, start=2):
        name = (row.get('Name') or row.get('name') or '').strip()
        email = (row.get('Email') or row.get('email') or '').strip()
        role_name = (row.get('Role') or row.get('role') or '').strip()
        pin = (row.get('PIN') or row.get('pin') or '').strip()

        # Validate required fields
        if not name or not email:
            result.errors.append((row_num, _('Missing name or email')))
            continue

        # Skip duplicates
        if LocalUser.objects.filter(hub_id=hub_id, email=email).exists():
            result.skipped += 1
            continue

        # Resolve role by name or display_name
        role_obj = None
        if role_name:
            role_obj = Role.objects.filter(
                hub_id=hub_id, is_active=True, is_deleted=False
            ).filter(
                Q(name__iexact=role_name) | Q(display_name__iexact=role_name)
            ).first()
        if not role_obj:
            role_obj = Role.objects.filter(
                hub_id=hub_id, name='employee', is_active=True, is_deleted=False
            ).first()

        # Default PIN if not valid
        if not pin or len(pin) != 4 or not pin.isdigit():
            pin = '0000'

        user = LocalUser.objects.create(
            hub_id=hub_id,
            email=email,
            name=name,
            role_obj=role_obj,
            role=role_obj.name if role_obj else 'employee',
        )
        user.set_pin(pin)
        result.created += 1

    # Build result message
    parts = []
    if result.created:
        parts.append(_('%(count)d imported') % {'count': result.created})
    if result.skipped:
        parts.append(_('%(count)d skipped (duplicates)') % {'count': result.skipped})
    if result.errors:
        parts.append(_('%(count)d errors') % {'count': len(result.errors)})

    if result.created:
        messages.success(request, ', '.join(str(p) for p in parts))
    elif result.errors:
        messages.error(request, ', '.join(str(p) for p in parts))
    else:
        messages.warning(request, ', '.join(str(p) for p in parts))

    return _render_list(request, hub_id)

"""
Views for roles management.
"""

from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _

from apps.accounts.decorators import admin_required
from apps.accounts.models import Role, Permission, RolePermission
from apps.core.services.permission_service import PermissionService
from apps.core.htmx import htmx_view
from apps.core.services import export_to_csv, export_to_excel

SORT_FIELDS = {
    'name': 'display_name',
    'users': 'user_count',
    'status': 'is_active',
}

PER_PAGE_CHOICES = [10, 25, 50, 100]


def _build_list_context(hub_id, per_page=10):
    """Build context dict for the roles list (used after mutations)."""
    roles = Role.objects.filter(
        hub_id=hub_id, is_deleted=False
    ).annotate(user_count=Count('users')).order_by('-is_system', 'display_name')

    paginator = Paginator(roles, per_page)
    page_obj = paginator.get_page(1)

    return {
        'roles': page_obj,
        'page_obj': page_obj,
        'search_query': '',
        'sort_field': 'name',
        'sort_dir': 'asc',
        'status_filter': '',
        'type_filter': '',
        'per_page': per_page,
    }


def _render_list(request, hub_id, per_page=10):
    """Render the roles list partial after a mutation."""
    context = _build_list_context(hub_id, per_page)
    return render(request, 'main/roles/partials/roles_list.html', context)


@admin_required
@htmx_view('main/roles/pages/index.html', 'main/roles/partials/content.html')
def role_list(request):
    """List all roles with search, sort, filter, pagination."""
    hub_id = request.session.get('hub_id')
    search_query = request.GET.get('q', '').strip()
    sort_field = request.GET.get('sort', 'name')
    sort_dir = request.GET.get('dir', 'asc')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    page_number = request.GET.get('page', 1)
    current_view = request.GET.get('view', 'table')
    per_page = int(request.GET.get('per_page', 10))
    if per_page not in PER_PAGE_CHOICES:
        per_page = 10

    roles = Role.objects.filter(
        hub_id=hub_id, is_deleted=False
    ).annotate(user_count=Count('users'))

    # Status filter
    if status_filter == 'active':
        roles = roles.filter(is_active=True)
    elif status_filter == 'inactive':
        roles = roles.filter(is_active=False)

    # Type filter
    if type_filter == 'system':
        roles = roles.filter(is_system=True)
    elif type_filter == 'custom':
        roles = roles.filter(is_system=False)

    # Search
    if search_query:
        roles = roles.filter(
            Q(name__icontains=search_query) |
            Q(display_name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Sort
    order_by = SORT_FIELDS.get(sort_field, 'display_name')
    if sort_dir == 'desc':
        order_by = f'-{order_by}'
    roles = roles.order_by(order_by)

    # Export
    export_format = request.GET.get('export')
    if export_format in ('csv', 'excel'):
        export_fields = ['display_name', 'name', 'description', 'is_system', 'is_active', 'user_count']
        export_headers = [
            str(_('Display Name')), str(_('Name')), str(_('Description')),
            str(_('System')), str(_('Active')), str(_('Users')),
        ]
        export_formatters = {
            'is_system': lambda v: str(_('Yes')) if v else str(_('No')),
            'is_active': lambda v: str(_('Active')) if v else str(_('Inactive')),
        }
        if export_format == 'csv':
            return export_to_csv(
                roles, fields=export_fields, headers=export_headers,
                field_formatters=export_formatters, filename='roles.csv',
            )
        return export_to_excel(
            roles, fields=export_fields, headers=export_headers,
            field_formatters=export_formatters, filename='roles.xlsx',
            sheet_name=str(_('Roles')),
        )

    paginator = Paginator(roles, per_page)
    page_obj = paginator.get_page(page_number)

    context = {
        'roles': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'current_view': current_view,
        'per_page': per_page,
    }

    # HTMX partial: swap only datatable body
    if request.headers.get('HX-Request') and request.headers.get('HX-Target') == 'datatable-body':
        return render(request, 'main/roles/partials/roles_list.html', context)

    context.update({
        'current_section': 'roles',
        'page_title': _('Roles'),
    })
    return context


@admin_required
@htmx_view('main/roles/pages/detail.html', 'main/roles/partials/detail.html')
def role_detail(request, role_id):
    """View role details and edit permissions."""
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    # Get modules with their permissions for the UI
    modules = PermissionService.get_modules_with_permissions(hub_id)

    # Get current role permissions (expanded from wildcards)
    expanded_permissions = role.get_all_permissions()

    # Get role wildcards as a set for easy lookup
    wildcards = set(
        RolePermission.objects.filter(
            role=role,
            is_deleted=False,
            wildcard__gt=''
        ).values_list('wildcard', flat=True)
    )

    # Get individual permissions (not from wildcards)
    individual_permissions = set(
        RolePermission.objects.filter(
            role=role,
            is_deleted=False,
            permission__isnull=False
        ).values_list('permission__codename', flat=True)
    )

    # Calculate module states for the UI
    for module in modules:
        module_wildcard = module['wildcard']
        has_wildcard = module_wildcard in wildcards

        # Count active permissions in this module
        active_count = sum(
            1 for p in module['permissions']
            if p['codename'] in expanded_permissions
        )
        total_count = len(module['permissions'])

        module['has_wildcard'] = has_wildcard
        module['active_count'] = active_count
        module['total_count'] = total_count
        module['is_full'] = active_count == total_count and total_count > 0
        module['is_partial'] = 0 < active_count < total_count

    return {
        'role': role,
        'modules': modules,
        'expanded_permissions': expanded_permissions,
        'individual_permissions': individual_permissions,
        'wildcards': wildcards,
        'page_title': role.display_name,
        'current_section': 'roles',
    }


@admin_required
@htmx_view('main/roles/pages/form.html', 'main/roles/partials/form.html')
def role_create(request):
    """Create a new role."""
    hub_id = request.session.get('hub_id')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip().lower()
        display_name = request.POST.get('display_name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, _('Role name is required.'))
            return redirect('main:roles:create')

        # Check if role exists
        if Role.objects.filter(hub_id=hub_id, name=name, is_deleted=False).exists():
            messages.error(request, _('A role with this name already exists.'))
            return redirect('main:roles:create')

        role = Role.objects.create(
            hub_id=hub_id,
            name=name,
            display_name=display_name or name.title(),
            description=description,
            is_system=False,
        )

        messages.success(request, _('Role created successfully.'))
        return redirect('main:roles:detail', role_id=role.id)

    return {
        'page_title': _('Create Role'),
        'current_section': 'roles',
    }


@admin_required
@htmx_view('main/roles/pages/form.html', 'main/roles/partials/form.html')
def role_edit(request, role_id):
    """Edit a role."""
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    if request.method == 'POST':
        display_name = request.POST.get('display_name', '').strip()
        description = request.POST.get('description', '').strip()

        if display_name:
            role.display_name = display_name
        role.description = description
        role.save()

        messages.success(request, _('Role updated successfully.'))
        return redirect('main:roles:detail', role_id=role.id)

    return {
        'role': role,
        'page_title': _('Edit Role'),
        'current_section': 'roles',
    }


@admin_required
@htmx_view('main/roles/pages/confirm_delete.html', 'main/roles/partials/confirm_delete.html')
def role_delete(request, role_id):
    """Delete a role (soft delete)."""
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    if role.is_system:
        messages.error(request, _('System roles cannot be deleted.'))
        return redirect('main:roles:list')

    # Check if role is assigned to users
    user_count = role.users.filter(is_deleted=False).count()
    if user_count > 0:
        messages.error(
            request,
            _('Cannot delete role. It is assigned to %(count)d user(s).') % {'count': user_count}
        )
        return redirect('main:roles:detail', role_id=role.id)

    if request.method == 'POST':
        role.delete()  # Soft delete by default in HubBaseModel
        messages.success(request, _('Role deleted successfully.'))
        return redirect('main:roles:list')

    return {
        'role': role,
        'page_title': _('Delete Role'),
        'current_section': 'roles',
    }


@admin_required
def role_toggle_active(request, role_id):
    """Toggle role active status."""
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    if role.is_system and role.name == 'admin':
        messages.error(request, _('Admin role cannot be deactivated.'))
        return redirect('main:roles:detail', role_id=role.id)

    role.is_active = not role.is_active
    role.save(update_fields=['is_active', 'updated_at'])

    if role.is_active:
        messages.success(request, _('Role activated.'))
    else:
        messages.success(request, _('Role deactivated.'))

    return redirect('main:roles:detail', role_id=role.id)


@admin_required
@require_POST
def bulk_action(request):
    """Bulk activate/deactivate/delete roles."""
    hub_id = request.session.get('hub_id')
    ids_str = request.POST.get('ids', '')
    action = request.POST.get('action', '')

    if not ids_str or not action:
        return _render_list(request, hub_id)

    ids = [uid.strip() for uid in ids_str.split(',') if uid.strip()]
    roles = Role.objects.filter(hub_id=hub_id, id__in=ids, is_deleted=False)

    # Exclude system roles from destructive actions
    if action in ('deactivate', 'delete'):
        system_count = roles.filter(is_system=True).count()
        roles = roles.exclude(is_system=True)
        if system_count:
            messages.warning(request, _('System roles were excluded from this action.'))

    count = roles.count()

    if action == 'activate':
        roles.update(is_active=True)
        messages.success(request, _('%(count)d roles activated.') % {'count': count})
    elif action == 'deactivate':
        roles.update(is_active=False)
        messages.success(request, _('%(count)d roles deactivated.') % {'count': count})
    elif action == 'delete':
        roles_with_users = roles.annotate(uc=Count('users')).filter(uc__gt=0)
        skipped = roles_with_users.count()
        deletable = roles.exclude(id__in=roles_with_users.values_list('id', flat=True))
        deleted = deletable.count()
        deletable.update(is_deleted=True)
        if skipped:
            messages.warning(request, _('%(count)d roles skipped (have assigned users).') % {'count': skipped})
        if deleted:
            messages.success(request, _('%(count)d roles deleted.') % {'count': deleted})

    return _render_list(request, hub_id)


@admin_required
def sync_permissions(request):
    """Sync permissions from all modules."""
    hub_id = request.session.get('hub_id')

    count = PermissionService.sync_all_module_permissions(hub_id)

    messages.success(
        request,
        _('Synced %(count)d permissions from modules.') % {'count': count}
    )
    return redirect('main:roles:list')


@admin_required
def create_default_roles(request):
    """Create default system roles."""
    hub_id = request.session.get('hub_id')

    roles = PermissionService.create_default_roles(hub_id)

    messages.success(
        request,
        _('Created %(count)d default roles.') % {'count': len(roles)}
    )
    return redirect('main:roles:list')

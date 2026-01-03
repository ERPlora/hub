"""
Views for roles management.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.utils.translation import gettext as _

from apps.accounts.decorators import admin_required
from apps.accounts.models import Role, Permission, RolePermission
from apps.core.services.permission_service import PermissionService
from apps.core.htmx import htmx_view


@admin_required
@htmx_view('main/roles/pages/index.html', 'main/roles/partials/list_content.html')
def role_list(request):
    """List all roles."""
    hub_id = request.session.get('hub_id')

    roles = Role.objects.filter(
        hub_id=hub_id,
        is_deleted=False
    ).prefetch_related('permissions', 'users').order_by('-is_system', 'name')

    return {
        'roles': roles,
        'page_title': _('Roles'),
        'current_section': 'roles',
    }


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

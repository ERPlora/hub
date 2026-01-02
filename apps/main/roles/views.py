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


@admin_required
def role_list(request):
    """List all roles."""
    hub_id = request.session.get('hub_id')

    roles = Role.objects.filter(
        hub_id=hub_id,
        is_deleted=False
    ).prefetch_related('permissions', 'users').order_by('-is_system', 'name')

    # user_count is calculated in template via role.users.count

    return render(request, 'main/roles/role_list.html', {
        'roles': roles,
        'page_title': _('Roles'),
        'page_type': 'list',
    })


@admin_required
def role_detail(request, role_id):
    """View role details and edit permissions."""
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    # Get permissions grouped by module
    permissions_by_module = PermissionService.get_permissions_by_module(hub_id)

    # Get current role permissions (expanded)
    role_permissions = role.get_all_permissions()

    # Get role wildcards
    wildcards = list(
        RolePermission.objects.filter(
            role=role,
            is_deleted=False,
            wildcard__gt=''
        ).values_list('wildcard', flat=True)
    )

    return render(request, 'main/roles/role_detail.html', {
        'role': role,
        'permissions_by_module': permissions_by_module,
        'role_permissions': role_permissions,
        'wildcards': wildcards,
        'page_title': role.display_name,
        'page_type': 'detail',
        'back_url': '/main/roles/',
    })


@admin_required
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

    return render(request, 'main/roles/role_form.html', {
        'page_title': _('Create Role'),
        'page_type': 'form',
        'back_url': '/main/roles/',
    })


@admin_required
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

    return render(request, 'main/roles/role_form.html', {
        'role': role,
        'page_title': _('Edit Role'),
        'page_type': 'form',
        'back_url': f'/main/roles/{role.id}/',
    })


@admin_required
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
        role.soft_delete()
        messages.success(request, _('Role deleted successfully.'))
        return redirect('main:roles:list')

    return render(request, 'main/roles/role_confirm_delete.html', {
        'role': role,
        'page_title': _('Delete Role'),
        'page_type': 'form',
        'back_url': f'/main/roles/{role.id}/',
    })


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

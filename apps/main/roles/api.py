"""
API endpoints for roles management.

These are HTMX-friendly endpoints that return HTML fragments.
"""

import json
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _

from apps.accounts.decorators import admin_required
from apps.accounts.models import Role, Permission, RolePermission


@admin_required
@require_POST
def update_role_permissions(request, role_id):
    """
    Update role permissions via HTMX.

    Expects JSON body with:
    {
        "add": ["perm.codename1", "perm.codename2"],
        "remove": ["perm.codename3"]
    }
    """
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    added = 0
    removed = 0

    # Add permissions
    for codename in data.get('add', []):
        try:
            perm = Permission.objects.get(
                hub_id=hub_id,
                codename=codename,
                is_deleted=False
            )
            RolePermission.objects.get_or_create(
                hub_id=hub_id,
                role=role,
                permission=perm,
                defaults={'wildcard': ''}
            )
            added += 1
        except Permission.DoesNotExist:
            pass

    # Remove permissions
    for codename in data.get('remove', []):
        try:
            perm = Permission.objects.get(
                hub_id=hub_id,
                codename=codename,
                is_deleted=False
            )
            RolePermission.objects.filter(
                hub_id=hub_id,
                role=role,
                permission=perm,
                is_deleted=False
            ).update(is_deleted=True)
            removed += 1
        except Permission.DoesNotExist:
            pass

    return JsonResponse({
        'success': True,
        'added': added,
        'removed': removed,
    })


@admin_required
@require_POST
def add_wildcard(request, role_id):
    """Add a wildcard permission pattern to a role."""
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    try:
        data = json.loads(request.body)
        wildcard = data.get('wildcard', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not wildcard:
        return JsonResponse({'error': 'Wildcard pattern required'}, status=400)

    # Validate wildcard format
    if '*' not in wildcard:
        return JsonResponse({'error': 'Invalid wildcard pattern'}, status=400)

    # Check if already exists
    exists = RolePermission.objects.filter(
        hub_id=hub_id,
        role=role,
        wildcard=wildcard,
        is_deleted=False
    ).exists()

    if exists:
        return JsonResponse({'error': 'Wildcard already exists'}, status=400)

    RolePermission.objects.create(
        hub_id=hub_id,
        role=role,
        permission=None,
        wildcard=wildcard,
    )

    return JsonResponse({
        'success': True,
        'wildcard': wildcard,
    })


@admin_required
@require_POST
def remove_wildcard(request, role_id, wildcard):
    """Remove a wildcard permission pattern from a role."""
    hub_id = request.session.get('hub_id')

    role = get_object_or_404(
        Role,
        id=role_id,
        hub_id=hub_id,
        is_deleted=False
    )

    # Prevent removing '*' from admin role
    if role.name == 'admin' and wildcard == '*':
        return JsonResponse({
            'error': 'Cannot remove full access from admin role'
        }, status=400)

    deleted = RolePermission.objects.filter(
        hub_id=hub_id,
        role=role,
        wildcard=wildcard,
        is_deleted=False
    ).update(is_deleted=True)

    if deleted:
        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Wildcard not found'}, status=404)

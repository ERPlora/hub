"""
Base API Classes and Permissions

Shared utilities for all API endpoints across apps.
"""
from rest_framework import permissions, serializers


# =============================================================================
# Permissions
# =============================================================================

class IsAuthenticated(permissions.BasePermission):
    """Check if user is authenticated via session."""

    def has_permission(self, request, view):
        return 'local_user_id' in request.session


class IsAdmin(permissions.BasePermission):
    """Check if user is an admin."""

    def has_permission(self, request, view):
        return (
            'local_user_id' in request.session and
            request.session.get('user_role') == 'admin'
        )


class HasPermission(permissions.BasePermission):
    """
    Check if user has required permission(s).

    Usage in ViewSet:
        permission_classes = [IsAuthenticated, HasPermission]
        required_permissions = ['inventory.view_product']

        # Or for different actions:
        permission_map = {
            'list': ['inventory.view_product'],
            'create': ['inventory.add_product'],
            'update': ['inventory.change_product'],
            'destroy': ['inventory.delete_product'],
        }
    """

    def has_permission(self, request, view):
        # Must be authenticated first
        if 'local_user_id' not in request.session:
            return False

        # Get current user
        from apps.accounts.models import LocalUser
        user_id = request.session.get('local_user_id')

        try:
            user = LocalUser.objects.get(pk=user_id, is_active=True, is_deleted=False)
        except LocalUser.DoesNotExist:
            return False

        # Admin has all permissions
        if user.get_role_name() == 'admin':
            return True

        # Check permission_map for action-specific permissions
        permission_map = getattr(view, 'permission_map', {})
        action = getattr(view, 'action', None)

        if action and action in permission_map:
            required = permission_map[action]
            return user.has_perms(required)

        # Check required_permissions for all actions
        required = getattr(view, 'required_permissions', [])
        if required:
            return user.has_perms(required)

        # No specific permissions required
        return True


# =============================================================================
# Base Serializers
# =============================================================================

class SuccessResponseSerializer(serializers.Serializer):
    """Generic success response."""
    success = serializers.BooleanField(default=True)
    message = serializers.CharField(required=False)


class ErrorResponseSerializer(serializers.Serializer):
    """Generic error response."""
    success = serializers.BooleanField(default=False)
    error = serializers.CharField()
    detail = serializers.CharField(required=False)

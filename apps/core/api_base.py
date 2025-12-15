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

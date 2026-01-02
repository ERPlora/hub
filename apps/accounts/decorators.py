"""
Custom decorators for Hub authentication and permissions.

The Hub uses session-based authentication with LocalUser model,
not Django's built-in User model. Therefore, we need custom decorators
that check for 'local_user_id' in request.session instead of request.user.

Decorators available:
- @login_required: Ensures user is logged in
- @role_required(*roles): Checks user has one of specified roles
- @permission_required(*perms): Checks user has required permissions
"""

from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _


def login_required(function=None, redirect_url=None):
    """
    Decorator for views that checks if the user is logged in via Hub session.

    Usage:
        @login_required
        def my_view(request):
            ...

    Or with custom redirect:
        @login_required(redirect_url='/custom-login/')
        def my_view(request):
            ...

    Args:
        function: The view function to decorate
        redirect_url: Custom URL to redirect to if not authenticated (default: 'auth:login')

    Returns:
        Decorated function that checks for 'local_user_id' in session
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Check if user is authenticated via Hub session
            if 'local_user_id' not in request.session:
                # Get redirect URL
                if redirect_url:
                    login_url = redirect_url
                else:
                    login_url = reverse('auth:login')

                # Add 'next' parameter to redirect back after login
                next_url = request.get_full_path()
                return redirect(f'{login_url}?next={next_url}')

            return view_func(request, *args, **kwargs)
        return _wrapped_view

    # Allow using @login_required or @login_required()
    if function:
        return decorator(function)
    return decorator


def role_required(*roles):
    """
    Decorator that checks if logged-in user has one of the specified roles.

    Usage:
        @login_required
        @role_required('admin', 'manager')
        def admin_view(request):
            ...

    Args:
        *roles: Variable number of role strings ('admin', 'manager', 'cashier', etc.)

    Returns:
        Decorated function that checks user role
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # First check if user is logged in
            if 'local_user_id' not in request.session:
                login_url = reverse('auth:login')
                next_url = request.get_full_path()
                return redirect(f'{login_url}?next={next_url}')

            # Check if user has required role
            user_role = request.session.get('user_role')
            if user_role not in roles:
                return HttpResponseForbidden(
                    _("You don't have permission to access this page.")
                )

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def _get_current_user(request):
    """
    Get the current LocalUser from session.

    Returns:
        LocalUser instance or None if not authenticated
    """
    from apps.accounts.models import LocalUser

    user_id = request.session.get('local_user_id')
    if not user_id:
        return None

    try:
        return LocalUser.objects.get(pk=user_id, is_active=True, is_deleted=False)
    except LocalUser.DoesNotExist:
        return None


def permission_required(*permissions, any_perm=False):
    """
    Decorator for views that checks if the user has required permissions.

    Supports permission codenames from module PERMISSIONS lists.
    Admin users automatically have all permissions.

    Usage:
        # Require single permission
        @permission_required('inventory.view_product')
        def product_list(request):
            ...

        # Require ALL permissions (default)
        @permission_required('inventory.view_product', 'inventory.change_product')
        def product_edit(request):
            ...

        # Require ANY of the permissions
        @permission_required('inventory.view_product', 'sales.view_sale', any_perm=True)
        def dashboard(request):
            ...

    Args:
        *permissions: Permission codenames to check (e.g., 'module.action_model')
        any_perm: If True, user needs ANY of the permissions. If False, needs ALL.

    Returns:
        Decorated function that checks user permissions
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # First check if user is logged in
            if 'local_user_id' not in request.session:
                login_url = reverse('auth:login')
                next_url = request.get_full_path()
                return redirect(f'{login_url}?next={next_url}')

            # Get the current user
            user = _get_current_user(request)
            if not user:
                login_url = reverse('auth:login')
                next_url = request.get_full_path()
                return redirect(f'{login_url}?next={next_url}')

            # Admin always passes
            if user.get_role_name() == 'admin':
                return view_func(request, *args, **kwargs)

            # No permissions specified = just needs to be logged in
            if not permissions:
                return view_func(request, *args, **kwargs)

            # Check permissions
            if any_perm:
                # User needs ANY of the permissions
                has_permission = any(user.has_perm(p) for p in permissions)
            else:
                # User needs ALL permissions
                has_permission = all(user.has_perm(p) for p in permissions)

            if not has_permission:
                return HttpResponseForbidden(
                    _("You don't have permission to access this page.")
                )

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def admin_required(view_func):
    """
    Decorator for views that require admin role.

    Shorthand for @permission_required with admin check.

    Usage:
        @admin_required
        def admin_only_view(request):
            ...
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # First check if user is logged in
        if 'local_user_id' not in request.session:
            login_url = reverse('auth:login')
            next_url = request.get_full_path()
            return redirect(f'{login_url}?next={next_url}')

        # Get the current user
        user = _get_current_user(request)
        if not user:
            login_url = reverse('auth:login')
            next_url = request.get_full_path()
            return redirect(f'{login_url}?next={next_url}')

        # Check admin role
        if user.get_role_name() != 'admin':
            return HttpResponseForbidden(
                _("Administrator access required.")
            )

        return view_func(request, *args, **kwargs)
    return _wrapped_view

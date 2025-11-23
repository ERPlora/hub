"""
Custom decorators for Hub authentication.

The Hub uses session-based authentication with LocalUser model,
not Django's built-in User model. Therefore, we need custom decorators
that check for 'local_user_id' in request.session instead of request.user.
"""

from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse


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
        redirect_url: Custom URL to redirect to if not authenticated (default: 'accounts:login')

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
                    login_url = reverse('accounts:login')

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
                login_url = reverse('accounts:login')
                next_url = request.get_full_path()
                return redirect(f'{login_url}?next={next_url}')

            # Check if user has required role
            user_role = request.session.get('user_role')
            if user_role not in roles:
                # You could redirect to an "access denied" page here
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("You don't have permission to access this page.")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

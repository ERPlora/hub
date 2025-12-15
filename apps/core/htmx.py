"""
HTMX utilities for SPA navigation.

Provides decorator and utilities for handling HTMX requests
to enable SPA-like navigation without full page reloads.
"""
from functools import wraps
from django.shortcuts import render


def htmx_view(full_template, partial_template):
    """
    Decorator for views that support both full page and HTMX partial rendering.

    When a request comes from HTMX (via hx-get, hx-post, etc.), only the partial
    template is rendered. For direct browser requests (refresh, deep links),
    the full template with layout is rendered.

    Usage:
        @htmx_view('main/index/pages/index.html', 'main/index/partials/content.html')
        def dashboard_index(request):
            return {'stats': get_stats()}  # Return context dict

    Args:
        full_template: Template path for full page (with layout)
        partial_template: Template path for partial content (HTMX swap)

    Returns:
        Decorated view function
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Call the view to get context
            result = view_func(request, *args, **kwargs)

            # If view returns HttpResponse directly, return it
            if hasattr(result, 'status_code'):
                return result

            # Otherwise, result should be context dict
            context = result if isinstance(result, dict) else {}

            # Check if HTMX request
            if request.headers.get('HX-Request'):
                return render(request, partial_template, context)

            # Full page request
            return render(request, full_template, context)

        return wrapper
    return decorator


def is_htmx_request(request):
    """Check if request is from HTMX"""
    return request.headers.get('HX-Request') == 'true'


def htmx_redirect(url):
    """
    Return HTMX redirect response.

    Use when you need to redirect after an HTMX request
    (e.g., after form submission).
    """
    from django.http import HttpResponse
    response = HttpResponse()
    response['HX-Redirect'] = url
    return response


def htmx_refresh():
    """
    Return HTMX refresh response.

    Triggers a full page refresh on the client.
    """
    from django.http import HttpResponse
    response = HttpResponse()
    response['HX-Refresh'] = 'true'
    return response

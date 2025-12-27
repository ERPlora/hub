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

    Supports ?partial=true query parameter for testing/debugging fragments
    directly in the browser without HTMX headers.

    Usage:
        @htmx_view('main/index/pages/index.html', 'main/index/partials/content.html')
        def dashboard_index(request):
            return {'stats': get_stats()}  # Return context dict

    Testing fragments:
        - Browser: /my-view/ → full page
        - Browser: /my-view/?partial=true → fragment only
        - HTMX: /my-view/ with HX-Request header → fragment only

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

            # Check if partial requested via HTMX or ?partial=true query param
            is_partial = request.headers.get('HX-Request') or request.GET.get('partial') == 'true'

            if is_partial:
                return render(request, partial_template, context)

            # Full page request
            return render(request, full_template, context)

        return wrapper
    return decorator


def is_htmx_request(request):
    """Check if request is from HTMX or has ?partial=true"""
    return request.headers.get('HX-Request') == 'true' or request.GET.get('partial') == 'true'


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


class InfiniteScrollPaginator:
    """
    Helper class for implementing infinite scroll pagination with HTMX.

    Usage in view:
        paginator = InfiniteScrollPaginator(queryset, per_page=20)
        page_data = paginator.get_page(request.GET.get('page', 1))

        return {
            'items': page_data['items'],
            'has_next': page_data['has_next'],
            'next_page': page_data['next_page'],
            'is_first_page': page_data['is_first_page'],
            'total_count': page_data['total_count'],
        }

    In template (items partial):
        {% for item in items %}
            <div class="item">{{ item.name }}</div>
        {% endfor %}

        {% if has_next %}
        <div class="infinite-scroll-loader"
             hx-get="{{ request.path }}?page={{ next_page }}"
             hx-trigger="revealed"
             hx-target="this"
             hx-swap="outerHTML"
             hx-include="[name='search'],[name='order_by']">
            <ion-spinner name="crescent"></ion-spinner>
        </div>
        {% else %}
        <div class="infinite-scroll-end">
            No more items
        </div>
        {% endif %}
    """

    def __init__(self, queryset, per_page=20):
        """
        Initialize paginator.

        Args:
            queryset: Django QuerySet to paginate
            per_page: Number of items per page (default: 20)
        """
        self.queryset = queryset
        self.per_page = per_page

    def get_page(self, page_number):
        """
        Get page data for the specified page number.

        Args:
            page_number: Page number (1-indexed), can be string or int

        Returns:
            dict with:
                - items: QuerySet slice for this page
                - has_next: bool if there are more pages
                - next_page: next page number (None if no more pages)
                - is_first_page: bool if this is the first page
                - total_count: total number of items
                - page_number: current page number
                - start_index: 1-indexed start position
                - end_index: 1-indexed end position
        """
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1

        if page_number < 1:
            page_number = 1

        total_count = self.queryset.count()
        total_pages = (total_count + self.per_page - 1) // self.per_page if total_count > 0 else 1

        # Ensure page number doesn't exceed total pages
        if page_number > total_pages:
            page_number = total_pages

        # Calculate slice
        start = (page_number - 1) * self.per_page
        end = start + self.per_page

        items = self.queryset[start:end]

        has_next = page_number < total_pages

        # Calculate 1-indexed positions for display
        start_index = start + 1 if total_count > 0 else 0
        end_index = min(end, total_count)

        return {
            'items': items,
            'has_next': has_next,
            'next_page': page_number + 1 if has_next else None,
            'is_first_page': page_number == 1,
            'total_count': total_count,
            'page_number': page_number,
            'total_pages': total_pages,
            'start_index': start_index,
            'end_index': end_index,
            'per_page': self.per_page,
        }


def infinite_scroll_view(full_template, partial_template, items_template):
    """
    Decorator for views with infinite scroll support.

    Similar to htmx_view but optimized for list views with pagination.

    - Full page request → renders full_template
    - HTMX request (page=1 or no page) → renders partial_template (includes headers/search)
    - HTMX request (page>1) → renders items_template only (just the items + loader)

    Usage:
        @infinite_scroll_view(
            'inventory/pages/products.html',
            'inventory/partials/products_content.html',
            'inventory/partials/products_items.html'
        )
        def products_list(request):
            from apps.core.htmx import InfiniteScrollPaginator

            queryset = Product.objects.filter(is_active=True)
            paginator = InfiniteScrollPaginator(queryset, per_page=20)
            page_data = paginator.get_page(request.GET.get('page', 1))

            return {
                'items': page_data['items'],
                **page_data,  # includes has_next, next_page, etc.
            }
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            result = view_func(request, *args, **kwargs)

            # If view returns HttpResponse directly, return it
            if hasattr(result, 'status_code'):
                return result

            context = result if isinstance(result, dict) else {}

            # Check request type
            is_htmx = request.headers.get('HX-Request') or request.GET.get('partial') == 'true'
            page = request.GET.get('page', '1')

            try:
                page_num = int(page)
            except (TypeError, ValueError):
                page_num = 1

            if not is_htmx:
                # Full page request
                return render(request, full_template, context)

            if page_num > 1:
                # Subsequent pages - only return items + loader
                return render(request, items_template, context)

            # First HTMX request - return partial with headers
            return render(request, partial_template, context)

        return wrapper
    return decorator

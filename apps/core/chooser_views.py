"""
Chooser HTMX Views

Endpoints that return HTML partials for the generic chooser component.
Mounted at /htmx/chooser/ in core/urls.py
"""

import math

from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.decorators import login_required
from apps.core.chooser import chooser_registry


@login_required
@require_GET
def chooser_search(request, model_key):
    """
    HTMX endpoint: search and paginate chooser results.

    GET /htmx/chooser/<model_key>/search/?q=...&page=1&filters=...

    Returns HTML partial with search results.
    """
    config = chooser_registry.get(model_key)
    if not config:
        raise Http404(f"No chooser registered for '{model_key}'")

    query = request.GET.get('q', '').strip()
    page = int(request.GET.get('page', 1))

    # Get base queryset
    qs = config.get_queryset(request)

    # Apply search
    if query:
        qs = config.search(qs, query)

    # Apply filters from GET params
    filter_values = {}
    for key in config.filters:
        value = request.GET.get(f'filter_{key}', '').strip()
        if value:
            filter_values[key] = value
    if filter_values:
        qs = config.apply_filters(qs, filter_values)

    # Paginate
    total = qs.count()
    per_page = config.per_page
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    items = qs[offset:offset + per_page]

    # Build item data for template
    results = []
    for obj in items:
        results.append({
            'pk': str(obj.pk),
            'label': config.get_display_value(obj),
            'subtitle': config.get_subtitle(obj),
            'image_url': config.get_image_url(obj),
        })

    context = {
        'results': results,
        'query': query,
        'page': page,
        'total_pages': total_pages,
        'total': total,
        'model_key': model_key,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'config': config,
    }

    return render(request, 'core/chooser/results.html', context)


@login_required
@require_GET
def chooser_filters(request, model_key):
    """
    HTMX endpoint: get filter options for a chooser.

    GET /htmx/chooser/<model_key>/filters/

    Returns HTML partial with filter dropdowns.
    """
    config = chooser_registry.get(model_key)
    if not config:
        raise Http404(f"No chooser registered for '{model_key}'")

    filters_data = []
    for key, filter_config in config.filters.items():
        choices = config.get_filter_choices(key, request)
        filters_data.append({
            'key': key,
            'label': filter_config.get('label', key),
            'choices': choices,
        })

    return render(request, 'core/chooser/filters.html', {
        'filters': filters_data,
        'model_key': model_key,
    })

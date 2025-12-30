"""
filter_bar component - Search bar with filters and action buttons.

Usage:
    {% component "filter_bar"
        search_url="/products/"
        search_target="#products-table-container"
        search_placeholder="Search products..."
        search_name="search"
        search_value=request.GET.search %}

        {% fill "filters" %}
            <select name="status" hx-get="..." hx-trigger="change">
                <option value="">All</option>
            </select>
            <input type="date" name="date_from" ...>
        {% endfill %}

        {% fill "actions" %}
            <ion-button fill="outline" onclick="importFile()">
                <ion-icon slot="icon-only" name="cloud-upload-outline"></ion-icon>
            </ion-button>
        {% endfill %}
    {% endcomponent %}
"""

from django_components import Component, register


@register("filter_bar")
class FilterBar(Component):
    template_name = "filter_bar/filter_bar.html"

    def get_context_data(
        self,
        search_url: str = "",
        search_target: str = "",
        search_placeholder: str = "Search...",
        search_name: str = "search",
        search_value: str = "",
        search_include: str = "",
        debounce_ms: int = 400,
        **kwargs
    ):
        return {
            "search_url": search_url,
            "search_target": search_target,
            "search_placeholder": search_placeholder,
            "search_name": search_name,
            "search_value": search_value or "",
            "search_include": search_include,
            "debounce_ms": debounce_ms,
            **kwargs,
        }

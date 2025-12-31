"""
list_page component - Complete list page structure with tabbar OOB swap.

Usage (new - recommended):
    {% component "list_page"
        title="Products"
        subtitle="Manage your inventory"
        action_label="New Product"
        action_url="/products/create/"
        action_hx_target="#main-content-area"
        module_id="inventory"
        tabbar_view="products" %}

        {% fill "stats" %}
            <!-- Optional stat cards -->
        {% endfill %}

        {% fill "filters" %}
            {% component "filter_bar" ... %}{% endcomponent %}
        {% endfill %}

        {% fill "content" %}
            {% component "data_table" ... %}{% endcomponent %}
        {% endfill %}
    {% endcomponent %}

Usage (legacy - for backwards compatibility):
    {% component "list_page"
        tabbar_template="inventory/partials/tabbar.html"
        tabbar_view="products" %}
        ...
    {% endcomponent %}
"""

from django_components import Component, register


@register("list_page")
class ListPage(Component):
    template_name = "list_page/list_page.html"

    def get_context_data(
        self,
        title: str = "",
        subtitle: str = "",
        action_label: str = "",
        action_url: str = "",
        action_icon: str = "add-outline",
        action_hx_target: str = "#main-content-area",
        module_id: str = "",
        tabbar_template: str = "",  # Legacy - kept for backwards compatibility
        tabbar_view: str = "",
        **kwargs
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "action_label": action_label,
            "action_url": action_url,
            "action_icon": action_icon,
            "action_hx_target": action_hx_target,
            "module_id": module_id,
            "tabbar_template": tabbar_template,
            "tabbar_view": tabbar_view,
            **kwargs,
        }

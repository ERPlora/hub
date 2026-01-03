"""
page component - Base page structure with ion-page, header, content, and optional tabbar.

This is the generic base component for all module pages. Use specialized components
(list_page, settings_page) when they fit your use case better.

Usage:
    {% component "page"
        title="Dashboard"
        subtitle="Overview of your inventory"
        module_id="inventory"
        tabbar_view="dashboard"
        action_icon="add-outline"
        action_url="/products/new/" %}

        {% fill "content" %}
            <!-- Page content here -->
        {% endfill %}
    {% endcomponent %}

Params:
    title: Page title shown in header
    subtitle: Optional subtitle
    module_id: Module ID for loading tabbar from module.json
    tabbar_view: Current view ID for marking active tab
    navigation: Navigation list from @module_view decorator (avoids reloading from module.py)
    show_back: Show back button (default True, auto-detected)
    action_icon: Icon for header action button
    action_label: Label for header action button
    action_url: URL for header action button (HTMX)
    padding: Add ion-padding to content (default True)
"""

from django_components import Component, register


@register("page")
class Page(Component):
    template_name = "page/page.html"

    def get_context_data(
        self,
        title: str = "",
        subtitle: str = "",
        module_id: str = "",
        tabbar_view: str = "",
        navigation: list = None,
        show_back: bool = True,
        action_icon: str = "",
        action_label: str = "",
        action_url: str = "",
        action_hx_target: str = "#main-content-area",
        action_x_click: str = "",
        padding: bool = True,
        render_tabbar: bool = False,
        **kwargs
    ):
        return {
            "title": title,
            "subtitle": subtitle,
            "module_id": module_id,
            "tabbar_view": tabbar_view,
            "navigation": navigation or [],
            "show_back": show_back,
            "action_icon": action_icon,
            "action_label": action_label,
            "action_url": action_url,
            "action_hx_target": action_hx_target,
            "action_x_click": action_x_click,
            "padding": padding,
            "render_tabbar": render_tabbar,
            **kwargs,
        }

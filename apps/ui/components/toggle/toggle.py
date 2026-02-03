"""
Toggle Component with HTMX

A reusable toggle (checkbox) wrapper that handles HTMX requests automatically.
Uses hx-vals='js:{}' to capture the toggle state on change.

Usage (standalone):
    {% component "toggle"
        name="allow_returns"
        checked=config.allow_returns
        hx_post="/m/returns/settings/toggle/" %}
    {% endcomponent %}

Usage (with label):
    {% component "toggle"
        name="allow_returns"
        checked=config.allow_returns
        title=_("Allow Returns")
        description=_("Enable product returns processing")
        hx_post="/m/returns/settings/toggle/" %}
    {% endcomponent %}

Usage (inside a list item):
    <div class="ux-list__item">
        {% component "toggle"
            name="show_timer"
            checked=config.show_timer
            title=_("Show Timer")
            hx_post="/m/sections/settings/toggle/" %}
        {% endcomponent %}
    </div>
"""

from django_components import Component, register


@register("toggle")
class Toggle(Component):
    template_name = "toggle/toggle.html"

    def get_context_data(
        self,
        name="",
        checked=False,
        disabled=False,
        color="",
        title="",
        description="",
        hx_post="",
        hx_target="",
        hx_swap="none",
        **kwargs
    ):
        """
        Args:
            name: Field name (used in hx-vals as 'name' parameter)
            checked: Initial checked state
            disabled: Whether toggle is disabled
            color: Toggle color (primary, success, warning, danger)
            title: Optional label title
            description: Optional description text
            hx_post: HTMX POST URL
            hx_target: HTMX target element
            hx_swap: HTMX swap mode (default: none)
        """
        return {
            "name": name,
            "checked": checked,
            "disabled": disabled,
            "color": color,
            "title": title,
            "description": description,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            **kwargs
        }

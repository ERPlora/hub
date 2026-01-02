"""
Select Field Component with HTMX

A reusable ion-select wrapper that handles HTMX requests automatically.
Uses hx-vals='js:{}' to capture the selected value on ionChange.

Usage:
    {% component "select_field"
        name="default_sort"
        value=config.default_sort
        options=sort_options
        label=_("Default Sort Order")
        hx_post="/m/customers/settings/select/" %}
    {% endcomponent %}

Options format:
    [
        {"value": "name", "label": "Name"},
        {"value": "date", "label": "Date"},
    ]
"""

from django_components import Component, register


@register("select_field")
class SelectField(Component):
    template_name = "select_field/select_field.html"

    def get_context_data(
        self,
        name="",
        value="",
        options=None,
        label="",
        label_placement="stacked",
        placeholder="",
        interface="popover",
        disabled=False,
        hx_post="",
        hx_target="",
        hx_swap="none",
        **kwargs
    ):
        """
        Args:
            name: Field name (used in hx-vals as 'name' parameter)
            value: Currently selected value
            options: List of dicts with 'value' and 'label' keys
            label: Select label
            label_placement: Label placement (stacked, floating, fixed)
            placeholder: Placeholder text
            interface: Ionic select interface (popover, action-sheet, alert)
            disabled: Whether select is disabled
            hx_post: HTMX POST URL
            hx_target: HTMX target element
            hx_swap: HTMX swap mode (default: none)
        """
        return {
            "name": name,
            "value": value,
            "options": options or [],
            "label": label,
            "label_placement": label_placement,
            "placeholder": placeholder,
            "interface": interface,
            "disabled": disabled,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            **kwargs
        }

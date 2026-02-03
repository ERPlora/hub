"""
Input Field Component with HTMX

A reusable input wrapper that handles HTMX requests automatically.
Uses hx-vals='js:{}' to capture the input value on change.

Usage:
    {% component "input_field"
        name="return_window_days"
        type="number"
        value=config.return_window_days
        min=0
        max=365
        label=_("Return Window (Days)")
        helper_text=_("Number of days after sale to allow returns")
        hx_post="/m/returns/settings/input/" %}
    {% endcomponent %}

Usage (with debounce for text input):
    {% component "input_field"
        name="store_name"
        value=config.store_name
        label=_("Store Name")
        hx_post="/m/settings/update/"
        debounce="500ms" %}
    {% endcomponent %}
"""

from django_components import Component, register


@register("input_field")
class InputField(Component):
    template_name = "input_field/input_field.html"

    def get_context_data(
        self,
        name="",
        type="text",
        value="",
        placeholder="",
        label="",
        label_placement="stacked",
        helper_text="",
        min=None,
        max=None,
        step=None,
        disabled=False,
        readonly=False,
        required=False,
        hx_post="",
        hx_target="",
        hx_swap="none",
        hx_trigger="change",
        debounce=None,
        **kwargs
    ):
        """
        Args:
            name: Field name (used in hx-vals as 'name' parameter)
            type: Input type (text, number, email, password, etc.)
            value: Initial value
            placeholder: Placeholder text
            label: Input label
            label_placement: Label placement (stacked, floating, fixed)
            helper_text: Helper text below input
            min: Minimum value (for number type)
            max: Maximum value (for number type)
            step: Step value (for number type)
            disabled: Whether input is disabled
            readonly: Whether input is readonly
            required: Whether input is required
            hx_post: HTMX POST URL
            hx_target: HTMX target element
            hx_swap: HTMX swap mode (default: none)
            hx_trigger: HTMX trigger event (default: change)
            debounce: Debounce delay (e.g., "500ms")
        """
        # Build trigger with optional debounce
        trigger = hx_trigger
        if debounce:
            trigger = f"{hx_trigger} delay:{debounce}"

        return {
            "name": name,
            "type": type,
            "value": value,
            "placeholder": placeholder,
            "label": label,
            "label_placement": label_placement,
            "helper_text": helper_text,
            "min": min,
            "max": max,
            "step": step,
            "disabled": disabled,
            "readonly": readonly,
            "required": required,
            "hx_post": hx_post,
            "hx_target": hx_target,
            "hx_swap": hx_swap,
            "hx_trigger": trigger,
            **kwargs
        }

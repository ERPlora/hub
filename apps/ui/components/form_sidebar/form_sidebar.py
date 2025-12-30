"""
Form Sidebar Component - django-components

Sliding sidebar panel for forms. Opens from the right side.
Uses Alpine.js $store.sidebar for state management.

Usage:
    In page template, include the sidebar container:
    {% component "form_sidebar" %}{% endcomponent %}

    Then trigger it with buttons:
    <ion-button hx-get="/products/new/"
                hx-target="#sidebar-content"
                @click="$store.sidebar.open('New Product')">
        New
    </ion-button>

    The form partial loaded via HTMX should contain the form fields.
"""

from django_components import Component, register


@register("form_sidebar")
class FormSidebar(Component):
    template_name = "form_sidebar/form_sidebar.html"
    # Include CSS with the component
    class Media:
        css = ["form_sidebar/form_sidebar.css"]

    def get_context_data(
        self,
        id="form-sidebar",
        width="380px",
        mobile_full_width=True,
        close_on_outside_click=True,
        **extra_attrs
    ):
        return {
            "id": id,
            "width": width,
            "mobile_full_width": mobile_full_width,
            "close_on_outside_click": close_on_outside_click,
            "extra_attrs": extra_attrs,
        }

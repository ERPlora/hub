"""
row_actions component - Standard View/Edit/Delete action buttons for table rows.

Usage:
    {% component "row_actions"
        view_url="/products/1/"
        edit_url="/products/1/edit/"
        delete_url="/products/1/delete/"
        delete_name="Product Name"
        hx_target="#dashboard-content" %}{% endcomponent %}

    Or with only some actions:
    {% component "row_actions"
        view_url="/products/1/"
        edit_url="/products/1/edit/" %}{% endcomponent %}
"""

from django_components import Component, register


@register("row_actions")
class RowActions(Component):
    template_name = "row_actions/row_actions.html"

    def get_context_data(
        self,
        view_url: str = "",
        edit_url: str = "",
        delete_url: str = "",
        delete_name: str = "",
        delete_method: str = "POST",
        hx_target: str = "#main-content-area",
        show_view: bool = True,
        show_edit: bool = True,
        show_delete: bool = True,
        **kwargs
    ):
        return {
            "view_url": view_url,
            "edit_url": edit_url,
            "delete_url": delete_url,
            "delete_name": delete_name,
            "delete_method": delete_method,
            "hx_target": hx_target,
            "show_view": show_view and bool(view_url),
            "show_edit": show_edit and bool(edit_url),
            "show_delete": show_delete and bool(delete_url),
            **kwargs,
        }

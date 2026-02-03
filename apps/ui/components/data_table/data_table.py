"""
data_table component - Sortable table with infinite scroll.

Usage:
    {% component "data_table"
        table_id="products-table-container"
        tbody_id="products-tbody"
        has_next=has_next
        next_page_url="/products/?page=2"
        total_count=total_count
        entity_name="product"
        entity_name_plural="products" %}

        {% fill "columns" %}
            <th class="sortable" hx-get="..." hx-vals='{"order_by": "name"}'>
                Name
                {% icon "chevron-up-outline" css_class="sort-icon" %}
            </th>
            <th class="cell-right">Price</th>
            <th class="cell-actions">Actions</th>
        {% endfill %}

        {% fill "rows" %}
            {% for item in items %}
            <tr>
                <td>{{ item.name }}</td>
                <td class="cell-right">{{ item.price }}</td>
                <td>{% component "row_actions" ... %}{% endcomponent %}</td>
            </tr>
            {% endfor %}
        {% endfill %}

        {% fill "empty" %}
            {% ui_empty_state title="No products" icon="cube-outline" %}
        {% endfill %}
    {% endcomponent %}
"""

from django_components import Component, register


@register("data_table")
class DataTable(Component):
    template_name = "data_table/data_table.html"

    def get_context_data(
        self,
        table_id: str = "table-container",
        tbody_id: str = "table-tbody",
        has_next: bool = False,
        next_page_url: str = "",
        total_count: int = 0,
        entity_name: str = "item",
        entity_name_plural: str = "",
        show_empty: bool = True,
        **kwargs
    ):
        if not entity_name_plural:
            entity_name_plural = entity_name + "s"

        return {
            "table_id": table_id,
            "tbody_id": tbody_id,
            "has_next": has_next,
            "next_page_url": next_page_url,
            "total_count": total_count,
            "entity_name": entity_name,
            "entity_name_plural": entity_name_plural,
            "show_empty": show_empty,
            **kwargs,
        }

"""
ERPlora Chooser Template Tags

Template tags for rendering the generic chooser component.

Usage in templates:
    {% load chooser %}

    {# Single select (e.g., choose one product) #}
    {% chooser "inventory.product" name="product_id" %}

    {# Single select with pre-selected value #}
    {% chooser "inventory.product" name="product_id" value=product.pk %}

    {# Multiple select #}
    {% chooser "inventory.product" name="products" multiple=True %}

    {# Multiple select with pre-selected values #}
    {% chooser "customers.customer" name="customer_ids" multiple=True values=selected_ids %}
"""

import json
import uuid

from django import template
from django.utils.safestring import mark_safe

from apps.core.chooser import chooser_registry

register = template.Library()


@register.inclusion_tag('core/chooser/modal.html', takes_context=True)
def chooser(context, model_key, name, value=None, values=None, multiple=False):
    """
    Render a chooser component for selecting model instances.

    Args:
        model_key: Model identifier (e.g., 'inventory.product')
        name: Form field name for the hidden input(s)
        value: Pre-selected value (single pk, for single-select)
        values: Pre-selected values (list of pks, for multi-select)
        multiple: Allow multiple selection

    Returns:
        Context dict for the chooser modal template
    """
    config = chooser_registry.get(model_key)
    chooser_id = str(uuid.uuid4()).replace('-', '')[:8]

    # Build selected items from value/values
    selected_items = []

    if config:
        if multiple and values:
            pk_list = values if isinstance(values, (list, tuple)) else [values]
            try:
                objects = config.model.objects.filter(pk__in=pk_list)
                for obj in objects:
                    selected_items.append({
                        'pk': str(obj.pk),
                        'label': config.get_display_value(obj),
                    })
            except Exception:
                pass
        elif value:
            try:
                obj = config.model.objects.get(pk=value)
                selected_items.append({
                    'pk': str(obj.pk),
                    'label': config.get_display_value(obj),
                })
            except Exception:
                pass

    return {
        'model_key': model_key,
        'name': name,
        'chooser_id': chooser_id,
        'config': config,
        'multiple': multiple,
        'value': value,
        'selected_items_json': json.dumps(selected_items),
        'csp_nonce': context.get('csp_nonce', ''),
    }

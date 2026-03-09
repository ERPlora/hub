"""
ERPlora References Template Tags

Template tags for displaying object references before deletion.

Usage in templates:
    {% load references %}

    {% get_references object as refs %}
    {% if refs.total_count > 0 %}
        {% include "core/references/reference_list.html" with references=refs %}
    {% endif %}
"""

from django import template
from apps.core.references import get_references

register = template.Library()


@register.simple_tag
def get_references_for(obj, max_items=5):
    """
    Get references for an object.

    Usage:
        {% load references %}
        {% get_references_for product as refs %}
        {{ refs.total_count }}
    """
    return get_references(obj, max_items=max_items)

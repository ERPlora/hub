"""
ERPlora Slots Template Tags

Template tags for rendering slots - extension points where modules can
inject UI components into templates of other modules.

Usage in templates:
    {% load slots %}

    <!-- Render all content registered for a slot -->
    {% render_slot 'sales.pos_header_start' %}

    <!-- Check if a slot has content -->
    {% if_slot 'sales.pos_sidebar' %}
        <div class="sidebar">
            {% render_slot 'sales.pos_sidebar' %}
        </div>
    {% endif_slot %}
"""

from django import template
from django.utils.safestring import mark_safe
from apps.core.slots import slots

register = template.Library()


@register.simple_tag(takes_context=True)
def render_slot(context, slot_name: str) -> str:
    """
    Render all content registered for a slot.

    Args:
        slot_name: Name of the slot (e.g., 'sales.pos_header_start')

    Returns:
        Combined HTML from all registered slot content

    Example:
        {% load slots %}
        {% render_slot 'sales.pos_header_start' %}
    """
    request = context.get('request')

    # Build context dict from template context
    ctx = {}
    try:
        ctx = context.flatten()
    except Exception:
        # If flatten fails, just use empty context
        pass

    html = slots.render_slot(slot_name, request=request, context=ctx)
    return mark_safe(html)


@register.simple_tag(takes_context=True)
def slot_has_content(context, slot_name: str) -> bool:
    """
    Check if a slot has any registered content.

    Useful for conditionally rendering wrapper elements.

    Example:
        {% if slot_has_content 'sales.pos_sidebar' %}
            <div class="sidebar">
                {% render_slot 'sales.pos_sidebar' %}
            </div>
        {% endif %}
    """
    return slots.has_content(slot_name)


@register.inclusion_tag('core/slots/slot_wrapper.html', takes_context=True)
def render_slot_with_wrapper(context, slot_name: str, wrapper_class: str = '', wrapper_tag: str = 'div'):
    """
    Render a slot with an optional wrapper element.

    The wrapper is only rendered if the slot has content.

    Args:
        slot_name: Name of the slot
        wrapper_class: CSS class(es) for the wrapper element
        wrapper_tag: HTML tag for the wrapper (default: 'div')

    Example:
        {% render_slot_with_wrapper 'sales.pos_sidebar' wrapper_class='sidebar-container' wrapper_tag='aside' %}
    """
    request = context.get('request')

    ctx = {}
    try:
        ctx = context.flatten()
    except Exception:
        pass

    has_content = slots.has_content(slot_name)
    content = ''

    if has_content:
        content = slots.render_slot(slot_name, request=request, context=ctx)

    return {
        'has_content': has_content,
        'content': mark_safe(content),
        'wrapper_class': wrapper_class,
        'wrapper_tag': wrapper_tag,
        'slot_name': slot_name,
    }


class SlotNode(template.Node):
    """
    Node for the if_slot block tag.
    """
    def __init__(self, slot_name, nodelist_true, nodelist_false=None):
        self.slot_name = slot_name
        self.nodelist_true = nodelist_true
        self.nodelist_false = nodelist_false or template.NodeList()

    def render(self, context):
        slot_name = self.slot_name.resolve(context)

        if slots.has_content(slot_name):
            return self.nodelist_true.render(context)
        else:
            return self.nodelist_false.render(context)


@register.tag('if_slot')
def do_if_slot(parser, token):
    """
    Conditional block that renders only if a slot has content.

    Usage:
        {% if_slot 'sales.pos_sidebar' %}
            <div class="sidebar">
                {% render_slot 'sales.pos_sidebar' %}
            </div>
        {% else_slot %}
            <p>No sidebar content</p>
        {% endif_slot %}
    """
    bits = token.split_contents()

    if len(bits) != 2:
        raise template.TemplateSyntaxError(
            f"'{bits[0]}' tag requires exactly one argument (slot name)"
        )

    slot_name = parser.compile_filter(bits[1])

    nodelist_true = parser.parse(('else_slot', 'endif_slot'))
    token = parser.next_token()

    if token.contents == 'else_slot':
        nodelist_false = parser.parse(('endif_slot',))
        parser.delete_first_token()
    else:
        nodelist_false = template.NodeList()

    return SlotNode(slot_name, nodelist_true, nodelist_false)


@register.simple_tag
def get_slot_debug_info(slot_name: str = None) -> dict:
    """
    Get debug information about registered slots.

    Useful for development to see what's registered where.

    Example:
        {% get_slot_debug_info as slot_info %}
        {{ slot_info }}

        {% get_slot_debug_info 'sales.pos_header' as header_info %}
        {{ header_info }}
    """
    all_slots = slots.get_registered_slots()

    if slot_name:
        return all_slots.get(slot_name, [])

    return all_slots

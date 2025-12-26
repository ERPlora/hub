"""
Template tags for module icons.

Supports:
- Local SVG icons from module's static/icons/ directory (inline rendering)
- Local PNG icons from module's static/icons/ directory (base64 img tag)
- Ionic icons as fallback

Usage:
    {% load module_icons %}

    {# Render module icon (auto-detects SVG/PNG or falls back to Ionic) #}
    {% module_icon module_id="sales" css_class="text-2xl" %}

    {# Render with explicit icon name #}
    {% module_icon icon="cart-outline" css_class="text-primary" %}

    {# Render inline SVG from path #}
    {% svg_icon path="modules/sales/static/icons/icon.svg" css_class="w-6 h-6" %}
"""
import os
import base64
import re
from pathlib import Path
from django import template
from django.conf import settings
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()


def get_svg_content(svg_path: Path) -> str | None:
    """
    Read SVG file content and return it.
    Returns None if file doesn't exist or is invalid.
    """
    if not svg_path.exists():
        return None

    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            # Basic validation: must contain <svg
            if '<svg' not in content.lower():
                return None
            return content
    except Exception:
        return None


def get_png_base64(png_path: Path) -> str | None:
    """
    Read PNG file and return base64 encoded string.
    Returns None if file doesn't exist or can't be read.
    """
    if not png_path.exists():
        return None

    try:
        with open(png_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception:
        return None


def add_svg_classes(svg_content: str, classes: str) -> str:
    """
    Add CSS classes to SVG element.
    Preserves existing classes if present.
    """
    if not classes:
        return svg_content

    # Find the opening <svg tag
    svg_tag_match = re.search(r'<svg([^>]*)>', svg_content, re.IGNORECASE)
    if not svg_tag_match:
        return svg_content

    tag_attrs = svg_tag_match.group(1)

    # Check if class attribute exists
    class_match = re.search(r'class=["\']([^"\']*)["\']', tag_attrs)
    if class_match:
        # Append to existing classes
        existing_classes = class_match.group(1)
        new_classes = f'{existing_classes} {classes}'
        new_attrs = tag_attrs.replace(class_match.group(0), f'class="{new_classes}"')
    else:
        # Add new class attribute
        new_attrs = f'{tag_attrs} class="{classes}"'

    return svg_content.replace(svg_tag_match.group(0), f'<svg{new_attrs}>')


def find_module_icon(module_id: str) -> dict | None:
    """
    Find icon file in module's static/icons/ directory.

    Priority:
    1. icon.svg (preferred - inline rendering)
    2. icon.png (fallback - base64 img tag)

    Returns dict with 'type' ('svg' or 'png') and content/data.
    Returns None if no icon found.
    """
    modules_dir = Path(settings.MODULES_DIR)

    # Check both active and inactive module directories
    for prefix in ['', '_']:
        module_dir = modules_dir / f'{prefix}{module_id}'
        icons_dir = module_dir / 'static' / 'icons'

        if not icons_dir.exists():
            continue

        # Priority 1: SVG (inline rendering)
        svg_path = icons_dir / 'icon.svg'
        svg_content = get_svg_content(svg_path)
        if svg_content:
            return {'type': 'svg', 'content': svg_content}

        # Priority 2: PNG (base64 img tag)
        png_path = icons_dir / 'icon.png'
        png_data = get_png_base64(png_path)
        if png_data:
            return {'type': 'png', 'data': png_data}

    return None


@register.simple_tag
def module_icon(module_id: str = None, icon: str = None, css_class: str = '', size: str = ''):
    """
    Render a module icon.

    Priority:
    1. SVG from module's static/icons/icon.svg (inline)
    2. PNG from module's static/icons/icon.png (base64 img)
    3. Ionic icon from module.json
    4. Default cube-outline icon

    Args:
        module_id: Module identifier (e.g., 'sales', 'inventory')
        icon: Explicit Ionic icon name (fallback)
        css_class: CSS classes to apply
        size: Size class (e.g., 'text-2xl', 'w-6 h-6')

    Returns:
        Safe HTML string with inline SVG, img tag, or ion-icon element
    """
    all_classes = f'{css_class} {size}'.strip()

    # Try to find icon in module directory
    if module_id:
        icon_info = find_module_icon(module_id)

        if icon_info:
            if icon_info['type'] == 'svg':
                svg_with_classes = add_svg_classes(icon_info['content'], all_classes)
                return mark_safe(svg_with_classes)

            elif icon_info['type'] == 'png':
                class_attr = f'class="{escape(all_classes)}"' if all_classes else ''
                return mark_safe(
                    f'<img src="data:image/png;base64,{icon_info["data"]}" '
                    f'{class_attr} alt="Module icon" />'
                )

    # Fallback to Ionic icon
    icon_name = icon or 'cube-outline'
    class_attr = f'class="{escape(all_classes)}"' if all_classes else ''
    return mark_safe(f'<ion-icon name="{escape(icon_name)}" {class_attr}></ion-icon>')


@register.simple_tag
def svg_icon(path: str, css_class: str = '', size: str = ''):
    """
    Render an inline SVG from a file path.

    Args:
        path: Path to SVG file (relative to MODULES_DIR or absolute)
        css_class: CSS classes to apply
        size: Size class (e.g., 'text-2xl', 'w-6 h-6')

    Returns:
        Safe HTML string with inline SVG or empty string if not found
    """
    all_classes = f'{css_class} {size}'.strip()

    # Handle relative paths
    if not os.path.isabs(path):
        # Try relative to MODULES_DIR first
        svg_path = Path(settings.MODULES_DIR) / path
        if not svg_path.exists():
            # Try relative to BASE_DIR
            svg_path = Path(settings.BASE_DIR) / path
    else:
        svg_path = Path(path)

    svg_content = get_svg_content(svg_path)
    if svg_content:
        svg_with_classes = add_svg_classes(svg_content, all_classes)
        return mark_safe(svg_with_classes)

    return ''


@register.inclusion_tag('core/components/module_icon.html')
def module_icon_component(module=None, module_id: str = None, icon: str = None,
                          css_class: str = '', size: str = 'text-2xl',
                          fallback_icon: str = 'cube-outline'):
    """
    Render module icon as a component with more options.

    This tag uses a template for more complex rendering scenarios.

    Args:
        module: Module metadata dict (from module_loader)
        module_id: Module identifier
        icon: Explicit icon name
        css_class: CSS classes
        size: Size class
        fallback_icon: Icon to use if nothing else is found

    Returns:
        Context for the component template
    """
    # Determine module_id from module dict if provided
    if module and isinstance(module, dict):
        module_id = module_id or module.get('module_id')
        icon = icon or module.get('icon')

    all_classes = f'{css_class} {size}'.strip()

    # Try to find icon
    icon_info = find_module_icon(module_id) if module_id else None

    # Prepare context
    context = {
        'icon_name': icon or fallback_icon,
        'css_class': css_class,
        'size': size,
        'all_classes': all_classes,
        'has_svg': False,
        'has_png': False,
        'svg_content': None,
        'png_data': None,
    }

    if icon_info:
        if icon_info['type'] == 'svg':
            context['has_svg'] = True
            context['svg_content'] = add_svg_classes(icon_info['content'], all_classes)
        elif icon_info['type'] == 'png':
            context['has_png'] = True
            context['png_data'] = icon_info['data']

    return context

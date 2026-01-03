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


def add_svg_classes(svg_content: str, classes: str, size_px: int = 24) -> str:
    """
    Add CSS classes and fixed size to SVG element.
    Preserves existing classes if present.

    Args:
        svg_content: The SVG content as string
        classes: CSS classes to add
        size_px: Size in pixels for width/height (default 24px)
    """
    # Find the opening <svg tag
    svg_tag_match = re.search(r'<svg([^>]*)>', svg_content, re.IGNORECASE)
    if not svg_tag_match:
        return svg_content

    tag_attrs = svg_tag_match.group(1)

    # Remove existing width/height to override
    tag_attrs = re.sub(r'\s*width=["\'][^"\']*["\']', '', tag_attrs)
    tag_attrs = re.sub(r'\s*height=["\'][^"\']*["\']', '', tag_attrs)

    # Add fixed size
    tag_attrs = f'{tag_attrs} width="{size_px}" height="{size_px}"'

    # Check if class attribute exists
    if classes:
        class_match = re.search(r'class=["\']([^"\']*)["\']', tag_attrs)
        if class_match:
            # Append to existing classes
            existing_classes = class_match.group(1)
            new_classes = f'{existing_classes} {classes}'
            tag_attrs = tag_attrs.replace(class_match.group(0), f'class="{new_classes}"')
        else:
            # Add new class attribute
            tag_attrs = f'{tag_attrs} class="{classes}"'

    return svg_content.replace(svg_tag_match.group(0), f'<svg{tag_attrs}>')


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


def size_to_px(size: str) -> int:
    """
    Convert Tailwind/Ionic size classes to pixels.

    Args:
        size: Size class like 'text-2xl', 'text-3xl', 'w-6', etc.

    Returns:
        Size in pixels (default 24)
    """
    size_map = {
        'text-xs': 12,
        'text-sm': 14,
        'text-base': 16,
        'text-lg': 18,
        'text-xl': 20,
        'text-2xl': 24,
        'text-3xl': 30,
        'text-4xl': 36,
        'text-5xl': 48,
        'text-6xl': 60,
        'w-4': 16,
        'w-5': 20,
        'w-6': 24,
        'w-8': 32,
        'w-10': 40,
        'w-12': 48,
    }

    for key, px in size_map.items():
        if key in size:
            return px

    return 24  # Default


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
    size_px = size_to_px(size)

    # Try to find icon in module directory
    if module_id:
        icon_info = find_module_icon(module_id)

        if icon_info:
            if icon_info['type'] == 'svg':
                svg_with_classes = add_svg_classes(icon_info['content'], all_classes, size_px)
                return mark_safe(svg_with_classes)

            elif icon_info['type'] == 'png':
                class_attr = f'class="{escape(all_classes)}"' if all_classes else ''
                return mark_safe(
                    f'<img src="data:image/png;base64,{icon_info["data"]}" '
                    f'width="{size_px}" height="{size_px}" '
                    f'{class_attr} alt="Module icon" />'
                )

    # Fallback to djicons (which uses Ionicons by default)
    from djicons import icon as render_icon
    icon_name = icon or 'cube-outline'
    return mark_safe(render_icon(icon_name, css_class=all_classes))


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
    size_px = size_to_px(size)

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
        svg_with_classes = add_svg_classes(svg_content, all_classes, size_px)
        return mark_safe(svg_with_classes)

    return ''


@register.inclusion_tag('ui/module_icon.html')
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
    size_px = size_to_px(size)

    # Try to find icon
    icon_info = find_module_icon(module_id) if module_id else None

    # Prepare context
    context = {
        'icon_name': icon or fallback_icon,
        'css_class': css_class,
        'size': size,
        'size_px': size_px,
        'all_classes': all_classes,
        'has_svg': False,
        'has_png': False,
        'svg_content': None,
        'png_data': None,
    }

    if icon_info:
        if icon_info['type'] == 'svg':
            context['has_svg'] = True
            context['svg_content'] = add_svg_classes(icon_info['content'], all_classes, size_px)
        elif icon_info['type'] == 'png':
            context['has_png'] = True
            context['png_data'] = icon_info['data']

    return context

"""
UI Components - Django Template Tags

Encapsulates Ionic components so views don't need to know about Ionic internals.

Usage:
    {% load ui %}

    # Atomic components (inclusion_tag)
    {% ui_button "Save" color="primary" %}
    {% ui_input name="email" label="Email" type="email" %}
    {% ui_nav_item label="Home" icon="home-outline" %}

    # Block components (custom parser)
    {% ui_card title="Stats" %}
        <p>Content here</p>
    {% endui_card %}
"""

from django import template
from django.utils.safestring import mark_safe
from django.template.base import token_kwargs

register = template.Library()


# =============================================================================
# BLOCK TAG HELPERS
# =============================================================================

def parse_token_args(parser, token):
    """
    Parse token arguments into args and kwargs.
    Supports: {% tag "arg1" kwarg1="value" kwarg2=variable %}
    """
    bits = token.split_contents()
    tag_name = bits[0]
    args = []
    kwargs = {}

    bits = bits[1:]
    for bit in bits:
        if '=' in bit:
            key, value = bit.split('=', 1)
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                kwargs[key] = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                kwargs[key] = value[1:-1]
            else:
                # It's a variable reference
                kwargs[key] = parser.compile_filter(value)
        else:
            # Positional argument
            if bit.startswith('"') and bit.endswith('"'):
                args.append(bit[1:-1])
            elif bit.startswith("'") and bit.endswith("'"):
                args.append(bit[1:-1])
            else:
                args.append(parser.compile_filter(bit))

    return tag_name, args, kwargs


class BlockTagNode(template.Node):
    """Base class for block tags with content."""

    def __init__(self, nodelist, args, kwargs):
        self.nodelist = nodelist
        self.args = args
        self.kwargs = kwargs

    def resolve_args(self, context):
        """Resolve all args and kwargs against context."""
        resolved_args = []
        for arg in self.args:
            if hasattr(arg, 'resolve'):
                resolved_args.append(arg.resolve(context))
            else:
                resolved_args.append(arg)

        resolved_kwargs = {}
        for key, value in self.kwargs.items():
            if hasattr(value, 'resolve'):
                resolved_kwargs[key] = value.resolve(context)
            else:
                resolved_kwargs[key] = value

        return resolved_args, resolved_kwargs


# =============================================================================
# BLOCK COMPONENTS - Cards, Panels, Forms, etc.
# =============================================================================

class CardNode(BlockTagNode):
    """{% ui_card title="Title" %}...{% endui_card %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)

        title = kwargs.get('title', '')
        subtitle = kwargs.get('subtitle', '')
        css_class = kwargs.get('css_class', '')

        # Build card HTML
        html = f'<ion-card class="ui-card{" " + css_class if css_class else ""}">'

        if title:
            html += '<ion-card-header>'
            html += f'<ion-card-title>{title}</ion-card-title>'
            if subtitle:
                html += f'<ion-card-subtitle>{subtitle}</ion-card-subtitle>'
            html += '</ion-card-header>'

        html += f'<ion-card-content>{content}</ion-card-content>'
        html += '</ion-card>'

        return html


@register.tag('ui_card')
def do_ui_card(parser, token):
    """
    Block tag for ion-card with content.

    Usage:
        {% ui_card title="My Card" subtitle="Optional" %}
            Card content here
        {% endui_card %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_card',))
    parser.delete_first_token()
    return CardNode(nodelist, args, kwargs)


class ListNode(BlockTagNode):
    """{% ui_list %}...{% endui_list %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)

        lines = kwargs.get('lines', 'full')
        inset = kwargs.get('inset', False)
        css_class = kwargs.get('css_class', '')

        attrs = [f'lines="{lines}"']
        if inset:
            attrs.append('inset="true"')
        if css_class:
            attrs.append(f'class="{css_class}"')

        return f'<ion-list {" ".join(attrs)}>{content}</ion-list>'


@register.tag('ui_list')
def do_ui_list(parser, token):
    """
    Block tag for ion-list.

    Usage:
        {% ui_list lines="none" %}
            {% ui_list_item label="Item 1" %}
        {% endui_list %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_list',))
    parser.delete_first_token()
    return ListNode(nodelist, args, kwargs)


class HeaderNode(BlockTagNode):
    """{% ui_header title="Page" %}...{% endui_header %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)

        title = kwargs.get('title', '')
        title_class = kwargs.get('title_class', 'header-title')
        color = kwargs.get('color', '')
        css_class = kwargs.get('css_class', '')

        # Build header HTML
        header_class = f' class="{css_class}"' if css_class else ''
        toolbar_color = f' color="{color}"' if color else ''

        html = f'<ion-header{header_class}>'
        html += f'<ion-toolbar{toolbar_color}>'

        # Content includes slots (start buttons, title, end buttons)
        html += content

        # Add title if provided and not already in content
        if title and '<!-- title -->' not in content:
            html += f'<ion-title class="{title_class}">{title}</ion-title>'

        html += '</ion-toolbar></ion-header>'

        return html


@register.tag('ui_header')
def do_ui_header(parser, token):
    """
    Block tag for page header with toolbar.

    Usage:
        {% ui_header title="Dashboard" %}
            {% ui_buttons_start %}
                {% ui_menu_button %}
            {% endui_buttons_start %}
            {% ui_buttons_end %}
                {% ui_theme_toggle %}
                {% ui_user_avatar_button %}
            {% endui_buttons_end %}
        {% endui_header %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_header',))
    parser.delete_first_token()
    return HeaderNode(nodelist, args, kwargs)


class ButtonsSlotNode(BlockTagNode):
    """{% ui_buttons_start %}...{% endui_buttons_start %}"""

    def __init__(self, nodelist, args, kwargs, slot):
        super().__init__(nodelist, args, kwargs)
        self.slot = slot

    def render(self, context):
        content = self.nodelist.render(context)
        return f'<ion-buttons slot="{self.slot}">{content}</ion-buttons>'


@register.tag('ui_buttons_start')
def do_ui_buttons_start(parser, token):
    """Buttons slot for start position."""
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_buttons_start',))
    parser.delete_first_token()
    return ButtonsSlotNode(nodelist, args, kwargs, 'start')


@register.tag('ui_buttons_end')
def do_ui_buttons_end(parser, token):
    """Buttons slot for end position."""
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_buttons_end',))
    parser.delete_first_token()
    return ButtonsSlotNode(nodelist, args, kwargs, 'end')


@register.simple_tag
def ui_title(text, css_class="header-title"):
    """Render ion-title."""
    class_attr = f' class="{css_class}"' if css_class else ''
    return mark_safe(f'<!-- title --><ion-title{class_attr}>{text}</ion-title>')


# Keep ui_toolbar as alias for backwards compatibility
class ToolbarNode(HeaderNode):
    """Alias for HeaderNode - {% ui_toolbar %}...{% endui_toolbar %}"""
    pass


@register.tag('ui_toolbar')
def do_ui_toolbar(parser, token):
    """
    Block tag for toolbar (alias for ui_header).

    Usage:
        {% ui_toolbar title="Settings" %}
            {% ui_buttons_start %}
                {% ui_icon_button icon="arrow-back-outline" %}
            {% endui_buttons_start %}
        {% endui_toolbar %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_toolbar',))
    parser.delete_first_token()
    return ToolbarNode(nodelist, args, kwargs)


class TabbarNode(BlockTagNode):
    """{% ui_tabbar %}...{% endui_tabbar %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)

        css_class = kwargs.get('css_class', '')
        class_attr = f' class="{css_class}"' if css_class else ''

        return f'<ion-footer><ion-tab-bar{class_attr}>{content}</ion-tab-bar></ion-footer>'


@register.tag('ui_tabbar')
def do_ui_tabbar(parser, token):
    """
    Block tag for tab bar.

    Usage:
        {% ui_tabbar %}
            {% ui_tab_button label="Home" icon="home-outline" %}
            {% ui_tab_button label="Settings" icon="settings-outline" %}
        {% endui_tabbar %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_tabbar',))
    parser.delete_first_token()
    return TabbarNode(nodelist, args, kwargs)


class FormCardNode(BlockTagNode):
    """{% ui_form_card title="Settings" %}...{% endui_form_card %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)

        title = kwargs.get('title', '')
        subtitle = kwargs.get('subtitle', '')
        action = kwargs.get('action', '')
        method = kwargs.get('method', 'post')
        hx_post = kwargs.get('hx_post', '')
        hx_target = kwargs.get('hx_target', '')
        hx_swap = kwargs.get('hx_swap', '')
        css_class = kwargs.get('css_class', '')

        # Get CSRF token from context
        csrf_token = context.get('csrf_token', '')

        html = f'<ion-card class="ui-form-card{" " + css_class if css_class else ""}">'

        if title:
            html += '<ion-card-header>'
            html += f'<ion-card-title>{title}</ion-card-title>'
            if subtitle:
                html += f'<ion-card-subtitle>{subtitle}</ion-card-subtitle>'
            html += '</ion-card-header>'

        html += '<ion-card-content>'

        # Form tag
        form_attrs = [f'method="{method}"']
        if action:
            form_attrs.append(f'action="{action}"')
        if hx_post:
            form_attrs.append(f'hx-post="{hx_post}"')
        if hx_target:
            form_attrs.append(f'hx-target="{hx_target}"')
        if hx_swap:
            form_attrs.append(f'hx-swap="{hx_swap}"')

        html += f'<form {" ".join(form_attrs)}>'
        if csrf_token:
            html += f'<input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">'
        html += content
        html += '</form>'
        html += '</ion-card-content></ion-card>'

        return html


@register.tag('ui_form_card')
def do_ui_form_card(parser, token):
    """
    Block tag for form card.

    Usage:
        {% ui_form_card title="Settings" hx_post="/save/" %}
            {% ui_input name="name" label="Name" %}
            {% ui_form_actions submit_label="Save" %}
        {% endui_form_card %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_form_card',))
    parser.delete_first_token()
    return FormCardNode(nodelist, args, kwargs)


# =============================================================================
# BUTTON COMPONENT
# =============================================================================

@register.inclusion_tag("ui/button.html")
def ui_button(
    label,
    color="primary",
    fill="solid",
    size="default",
    expand=None,
    disabled=False,
    icon=None,
    icon_slot="start",
    href=None,
    hx_get=None,
    hx_post=None,
    hx_target=None,
    hx_swap=None,
    hx_push_url=None,
    hx_confirm=None,
    x_click=None,
    x_show=None,
    type="button",
    css_class="",
    **kwargs
):
    """
    Render an Ionic button.

    Args:
        label: Button text
        color: primary, secondary, success, warning, danger, light, medium, dark
        fill: solid, outline, clear
        size: small, default, large
        expand: block, full (optional)
        disabled: True/False
        icon: Ionicon name (e.g., "add-outline")
        icon_slot: start, end, icon-only
        href: URL for link button
        hx_get/hx_post: HTMX attributes
        hx_target: HTMX target
        hx_swap: HTMX swap method
        hx_push_url: HTMX push URL
        hx_confirm: HTMX confirmation dialog (preferred over Alpine.js)
        x_click: Alpine.js @click handler (use only when HTMX can't solve it)
        x_show: Alpine.js x-show directive
        type: button, submit, reset
        css_class: Additional CSS classes
    """
    return {
        "label": label,
        "color": color,
        "fill": fill,
        "size": size,
        "expand": expand,
        "disabled": disabled,
        "icon": icon,
        "icon_slot": icon_slot,
        "href": href,
        "hx_get": hx_get,
        "hx_post": hx_post,
        "hx_target": hx_target,
        "hx_swap": hx_swap,
        "hx_push_url": hx_push_url,
        "hx_confirm": hx_confirm,
        "x_click": x_click,
        "x_show": x_show,
        "type": type,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


@register.inclusion_tag("ui/icon_button.html")
def ui_icon_button(
    icon,
    color="medium",
    fill="clear",
    size="default",
    disabled=False,
    href=None,
    hx_get=None,
    hx_post=None,
    hx_target=None,
    hx_swap=None,
    hx_push_url=None,
    aria_label=None,
    css_class="",
    **kwargs
):
    """Render an icon-only button."""
    return {
        "icon": icon,
        "color": color,
        "fill": fill,
        "size": size,
        "disabled": disabled,
        "href": href,
        "hx_get": hx_get,
        "hx_post": hx_post,
        "hx_target": hx_target,
        "hx_swap": hx_swap,
        "hx_push_url": hx_push_url,
        "aria_label": aria_label,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


# =============================================================================
# CARD COMPONENT
# =============================================================================

@register.inclusion_tag("ui/stat_card.html")
def ui_stat_card(
    value,
    label,
    icon=None,
    color="primary",
    trend=None,
    trend_value=None,
    css_class="",
):
    """
    Render a statistics card.

    Args:
        value: The main value to display
        label: Description label
        icon: Ionicon name
        color: primary, success, warning, danger
        trend: up, down (optional)
        trend_value: Trend percentage or value
    """
    return {
        "value": value,
        "label": label,
        "icon": icon,
        "color": color,
        "trend": trend,
        "trend_value": trend_value,
        "css_class": css_class,
    }


# =============================================================================
# INPUT COMPONENTS
# =============================================================================

@register.inclusion_tag("ui/input.html")
def ui_input(
    name,
    label=None,
    type="text",
    value="",
    placeholder="",
    required=False,
    disabled=False,
    readonly=False,
    helper_text=None,
    error_text=None,
    icon=None,
    icon_slot="start",
    label_placement="floating",
    maxlength=None,
    pattern=None,
    css_class="",
    **kwargs
):
    """
    Render an Ionic input field.

    Args:
        name: Input name attribute
        label: Label text
        type: text, email, password, number, tel, url, date, time, datetime-local
        value: Initial value
        placeholder: Placeholder text
        required: True/False
        disabled: True/False
        readonly: True/False
        helper_text: Help text below input
        error_text: Error message
        icon: Ionicon name
        icon_slot: start, end
        label_placement: floating, stacked, fixed, start, end
        maxlength: Maximum input length
        pattern: Validation pattern (regex)
    """
    return {
        "name": name,
        "label": label,
        "type": type,
        "value": value,
        "placeholder": placeholder,
        "required": required,
        "disabled": disabled,
        "readonly": readonly,
        "helper_text": helper_text,
        "error_text": error_text,
        "icon": icon,
        "icon_slot": icon_slot,
        "label_placement": label_placement,
        "maxlength": maxlength,
        "pattern": pattern,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


@register.inclusion_tag("ui/select.html")
def ui_select(
    name,
    label=None,
    options=None,
    value="",
    placeholder="Select...",
    required=False,
    disabled=False,
    multiple=False,
    helper_text=None,
    error_text=None,
    label_placement="floating",
    interface="popover",
    css_class="",
    **kwargs
):
    """
    Render an Ionic select.

    Args:
        options: List of dicts with 'value' and 'label' keys,
                 or list of tuples (value, label)
        label_placement: floating, stacked, fixed, start, end
        interface: popover, action-sheet, alert
    """
    # Normalize options format
    normalized_options = []
    if options:
        for opt in options:
            if isinstance(opt, dict):
                normalized_options.append(opt)
            elif isinstance(opt, (list, tuple)) and len(opt) >= 2:
                normalized_options.append({"value": opt[0], "label": opt[1]})
            else:
                normalized_options.append({"value": opt, "label": opt})

    return {
        "name": name,
        "label": label,
        "options": normalized_options,
        "value": value,
        "placeholder": placeholder,
        "required": required,
        "disabled": disabled,
        "multiple": multiple,
        "helper_text": helper_text,
        "error_text": error_text,
        "label_placement": label_placement,
        "interface": interface,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


@register.inclusion_tag("ui/file_input.html")
def ui_file_input(
    name,
    label="Choose file",
    accept=None,
    multiple=False,
    required=False,
    disabled=False,
    icon="cloud-upload-outline",
    color="medium",
    fill="outline",
    size="default",
    show_filename=True,
    input_id=None,
    css_class="",
):
    """
    Render a styled file input with hidden native input.

    Args:
        name: Input name attribute
        label: Button label text
        accept: Accepted file types (e.g., "image/*", ".pdf,.doc")
        multiple: Allow multiple file selection
        required: Mark as required
        disabled: Disable the input
        icon: Ionicon name for button
        color: Button color (primary, medium, etc.)
        fill: Button fill (solid, outline, clear)
        size: Button size (small, default, large)
        show_filename: Show selected filename next to button
        input_id: Custom input ID (defaults to name)
    """
    return {
        "name": name,
        "label": label,
        "accept": accept,
        "multiple": multiple,
        "required": required,
        "disabled": disabled,
        "icon": icon,
        "color": color,
        "fill": fill,
        "size": size,
        "show_filename": show_filename,
        "input_id": input_id or name,
        "css_class": css_class,
    }


# =============================================================================
# LIST COMPONENTS
# =============================================================================

@register.inclusion_tag("ui/list_item.html")
def ui_list_item(
    label,
    detail=None,
    icon=None,
    avatar=None,
    href=None,
    hx_get=None,
    hx_target=None,
    hx_push_url=None,
    button=False,
    lines="full",
    css_class="",
    **kwargs
):
    """
    Render an Ionic list item.

    Args:
        label: Main text
        detail: Secondary text
        icon: Ionicon name (start slot)
        avatar: Avatar image URL
        href: Link URL
        button: Make item clickable
        lines: full, inset, none
    """
    return {
        "label": label,
        "detail": detail,
        "icon": icon,
        "avatar": avatar,
        "href": href,
        "hx_get": hx_get,
        "hx_target": hx_target,
        "hx_push_url": hx_push_url,
        "button": button,
        "lines": lines,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


# =============================================================================
# BADGE & CHIP COMPONENTS
# =============================================================================

@register.inclusion_tag("ui/badge.html")
def ui_badge(label, color="primary", css_class=""):
    """Render an Ionic badge."""
    return {
        "label": label,
        "color": color,
        "css_class": css_class,
    }


@register.inclusion_tag("ui/chip.html")
def ui_chip(
    label,
    color="primary",
    outline=False,
    icon=None,
    closable=False,
    css_class="",
    **kwargs
):
    """Render an Ionic chip."""
    return {
        "label": label,
        "color": color,
        "outline": outline,
        "icon": icon,
        "closable": closable,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


# =============================================================================
# AVATAR COMPONENT
# =============================================================================

@register.inclusion_tag("ui/avatar.html")
def ui_avatar(
    src=None,
    initials=None,
    alt="",
    size="md",
    color="primary",
    css_class="",
):
    """
    Render an avatar.

    Args:
        src: Image URL
        initials: Fallback initials if no image
        alt: Alt text
        size: sm, md, lg, xl
        color: Background color for initials
    """
    return {
        "src": src,
        "initials": initials,
        "alt": alt,
        "size": size,
        "color": color,
        "css_class": css_class,
    }


# =============================================================================
# EMPTY STATE COMPONENT
# =============================================================================

@register.inclusion_tag("ui/empty_state.html")
def ui_empty_state(
    title,
    description=None,
    icon=None,
    action_label=None,
    action_url=None,
    action_hx_get=None,
    action_hx_target=None,
    css_class="",
):
    """
    Render an empty state placeholder.

    Args:
        title: Main message
        description: Secondary message
        icon: Ionicon name
        action_label: Button text
        action_url: Button URL
        action_hx_get: HTMX get URL
        action_hx_target: HTMX target
    """
    return {
        "title": title,
        "description": description,
        "icon": icon,
        "action_label": action_label,
        "action_url": action_url,
        "action_hx_get": action_hx_get,
        "action_hx_target": action_hx_target,
        "css_class": css_class,
    }


# =============================================================================
# LAYOUT COMPONENTS
# =============================================================================

@register.inclusion_tag("ui/content_header.html", takes_context=True)
def ui_page_header(
    context,
    title,
    subtitle=None,
    back_url=None,
    back_hx_get=None,
    back_hx_target=None,
    back_hx_push_url=None,
    action_icon=None,
    action_label=None,
    action_color=None,
    action_badge=None,
    action_badge_color="danger",
    action_href=None,
    action_hx_get=None,
    action_hx_post=None,
    action_hx_target=None,
    action_hx_push_url=None,
    action_x_click=None,
    show_back=True,
):
    """
    Render a page header with optional back button and action button.

    The back button is automatically shown using the back_url from the
    navigation_context processor, unless explicitly disabled with show_back=False
    or overridden with back_url/back_hx_get.

    Args:
        title: Page title
        subtitle: Optional subtitle
        back_url: URL for back button (regular link) - overrides auto back_url
        back_hx_get: HTMX URL for back button - overrides auto back_url
        back_hx_target: HTMX target for back button (default: #main-content-area)
        back_hx_push_url: HTMX push-url for back button (default: true)
        action_icon: Icon for action button (e.g., "add-outline")
        action_label: Text label for action button
        action_color: Color for action button
        action_badge: Badge count/text for action button
        action_badge_color: Badge color (default: danger)
        action_href: URL for action button (regular link)
        action_hx_get: HTMX GET URL for action button
        action_hx_post: HTMX POST URL for action button
        action_hx_target: HTMX target for action button
        action_hx_push_url: HTMX push-url for action button
        action_x_click: Alpine.js click handler for action button
        show_back: If False, never show back button (default: True)
    """
    # Auto-detect back URL from context if not explicitly provided
    auto_back_url = context.get("back_url") if show_back else None

    # Use explicit back_hx_get if provided, otherwise use auto back_url for HTMX nav
    final_back_hx_get = back_hx_get
    if not final_back_hx_get and not back_url and auto_back_url:
        final_back_hx_get = auto_back_url

    return {
        "title": title,
        "subtitle": subtitle,
        "back_url": back_url,
        "back_hx_get": final_back_hx_get,
        "back_hx_target": back_hx_target or "#main-content-area",
        "back_hx_push_url": back_hx_push_url if back_hx_push_url is not None else "true",
        "action_icon": action_icon,
        "action_label": action_label,
        "action_color": action_color,
        "action_badge": action_badge,
        "action_badge_color": action_badge_color,
        "action_href": action_href,
        "action_hx_get": action_hx_get,
        "action_hx_post": action_hx_post,
        "action_hx_target": action_hx_target,
        "action_hx_push_url": action_hx_push_url,
        "action_x_click": action_x_click,
    }


@register.simple_tag
def ui_grid_start(padding=True):
    """Start an Ionic grid."""
    padding_attr = "" if padding else ' class="ion-no-padding"'
    return mark_safe(f"<ion-grid{padding_attr}>")


@register.simple_tag
def ui_grid_end():
    """End an Ionic grid."""
    return mark_safe("</ion-grid>")


@register.simple_tag
def ui_row_start(css_class=""):
    """Start an Ionic row."""
    class_attr = f' class="{css_class}"' if css_class else ""
    return mark_safe(f"<ion-row{class_attr}>")


@register.simple_tag
def ui_row_end():
    """End an Ionic row."""
    return mark_safe("</ion-row>")


@register.simple_tag
def ui_col_start(size="12", size_sm=None, size_md=None, size_lg=None, size_xl=None, css_class=""):
    """
    Start an Ionic column.

    Args:
        size: Default column size (1-12)
        size_sm: Size at sm breakpoint
        size_md: Size at md breakpoint
        size_lg: Size at lg breakpoint
        size_xl: Size at xl breakpoint
    """
    attrs = [f'size="{size}"']
    if size_sm:
        attrs.append(f'size-sm="{size_sm}"')
    if size_md:
        attrs.append(f'size-md="{size_md}"')
    if size_lg:
        attrs.append(f'size-lg="{size_lg}"')
    if size_xl:
        attrs.append(f'size-xl="{size_xl}"')
    if css_class:
        attrs.append(f'class="{css_class}"')
    return mark_safe(f"<ion-col {' '.join(attrs)}>")


@register.simple_tag
def ui_col_end():
    """End an Ionic column."""
    return mark_safe("</ion-col>")


# =============================================================================
# LAYOUT COMPONENTS - Navigation
# =============================================================================

@register.inclusion_tag("ui/nav_item.html")
def ui_nav_item(
    label,
    icon=None,
    url=None,
    hx_get=None,
    hx_target=None,
    hx_push_url=True,
    active=False,
    badge=None,
    detail=False,
    lines="none",
    css_class="",
    **kwargs
):
    """
    Render a navigation item for sidebar/menu.

    Args:
        label: Item text
        icon: Ionicon name
        url: Navigation URL
        hx_get: HTMX URL
        hx_target: HTMX target
        hx_push_url: Push URL to history
        active: Is current item active
        badge: Badge text/number
        detail: Show chevron
        lines: Item lines (none, full, inset)
    """
    return {
        "label": label,
        "icon": icon,
        "url": url,
        "hx_get": hx_get,
        "hx_target": hx_target,
        "hx_push_url": hx_push_url,
        "active": active,
        "badge": badge,
        "detail": detail,
        "lines": lines,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


@register.inclusion_tag("ui/nav_group.html")
def ui_nav_group(label=None, css_class=""):
    """
    Render a navigation group header/divider.

    Args:
        label: Group label (optional)
    """
    return {
        "label": label,
        "css_class": css_class,
    }


@register.inclusion_tag("ui/tab_button.html")
def ui_tab_button(
    label,
    icon=None,
    url=None,
    hx_get=None,
    hx_target=None,
    hx_push_url=True,
    active=False,
    badge=None,
    css_class="",
    **kwargs
):
    """
    Render a tab bar button.

    Args:
        label: Tab label
        icon: Ionicon name
        url: Navigation URL
        hx_get: HTMX URL
        hx_target: HTMX target
        hx_push_url: Push URL to history
        active: Is current tab active
        badge: Badge text/number
    """
    return {
        "label": label,
        "icon": icon,
        "url": url,
        "hx_get": hx_get,
        "hx_target": hx_target,
        "hx_push_url": hx_push_url,
        "active": active,
        "badge": badge,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


@register.inclusion_tag("ui/menu_button.html")
def ui_menu_button(menu_id="main-menu", css_class=""):
    """
    Render a menu toggle button.

    Args:
        menu_id: ID of the menu to toggle
    """
    return {
        "menu_id": menu_id,
        "css_class": css_class,
    }


@register.inclusion_tag("ui/back_button.html", takes_context=True)
def ui_back_button(context, css_class=""):
    """
    Render a back button that navigates to the appropriate parent page.

    Uses the back_url from navigation_context processor.
    Only renders if back_url is available (not on home page).

    Args:
        css_class: Additional CSS classes
    """
    return {
        "back_url": context.get("back_url"),
        "css_class": css_class,
    }


@register.inclusion_tag("ui/user_avatar_button.html")
def ui_user_avatar_button(
    initials=None,
    email=None,
    src=None,
    size="md",
    color="primary",
    action_sheet_id=None,
    css_class="",
    **kwargs
):
    """
    Render a user avatar button for header.

    Args:
        initials: User initials (fallback)
        email: User email (extracts first letter)
        src: Avatar image URL
        size: sm, md, lg
        color: Avatar background color
        action_sheet_id: ID of action sheet to trigger
    """
    # Extract initials from email if not provided
    if not initials and email:
        initials = email[0].upper() if email else "?"
    return {
        "initials": initials or "?",
        "src": src,
        "size": size,
        "color": color,
        "action_sheet_id": action_sheet_id,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


@register.inclusion_tag("ui/theme_toggle.html")
def ui_theme_toggle(css_class=""):
    """
    Render a theme toggle button (dark/light mode).
    """
    return {
        "css_class": css_class,
    }


# =============================================================================
# SIMPLE TAGS (Non-pair tags)
# =============================================================================

@register.simple_tag
def ui_list_start(lines="full", inset=False, css_class=""):
    """Start an ion-list."""
    attrs = []
    if lines:
        attrs.append(f'lines="{lines}"')
    if inset:
        attrs.append('inset="true"')
    if css_class:
        attrs.append(f'class="{css_class}"')
    return mark_safe(f"<ion-list {' '.join(attrs)}>")


@register.simple_tag
def ui_list_end():
    """End an ion-list."""
    return mark_safe("</ion-list>")


@register.simple_tag
def ui_tabbar_start(css_class=""):
    """Start an ion-tab-bar."""
    class_attr = f' class="{css_class}"' if css_class else ""
    return mark_safe(f"<ion-footer><ion-tab-bar{class_attr}>")


@register.simple_tag
def ui_tabbar_end():
    """End an ion-tab-bar."""
    return mark_safe("</ion-tab-bar></ion-footer>")


@register.simple_tag
def ui_content_start(padding=True, fullscreen=False, css_class=""):
    """Start an ion-content area."""
    attrs = []
    if not padding:
        attrs.append('class="ion-no-padding"')
    elif css_class:
        attrs.append(f'class="{css_class}"')
    if fullscreen:
        attrs.append('fullscreen="true"')
    return mark_safe(f"<ion-content {' '.join(attrs)}>")


@register.simple_tag
def ui_content_end():
    """End an ion-content area."""
    return mark_safe("</ion-content>")


# =============================================================================
# HEADER SPECIFIC COMPONENTS
# =============================================================================

@register.inclusion_tag("ui/connection_status.html")
def ui_connection_status(url, interval="30s", css_class=""):
    """
    Render connection status indicator with HTMX polling.

    Args:
        url: URL to check connection status
        interval: Polling interval (default 30s)
        css_class: Additional CSS classes
    """
    return {
        "url": url,
        "interval": interval,
        "css_class": css_class,
    }


@register.inclusion_tag("ui/fullscreen_button.html")
def ui_fullscreen_button(css_class=""):
    """
    Render fullscreen toggle button.
    Uses Alpine.js for state management.
    """
    return {
        "css_class": css_class,
    }


@register.inclusion_tag("ui/pwa_install_button.html")
def ui_pwa_install_button(label=None, css_class=""):
    """
    Render PWA install button.
    Only visible when app is installable (uses Alpine.js canInstall).

    Args:
        label: Button label (optional, hidden on mobile if provided)
        css_class: Additional CSS classes
    """
    return {
        "label": label,
        "css_class": css_class,
    }


@register.simple_tag
def ui_header_action_button(icon, alpine_click=None, onclick=None, color="", css_class=""):
    """
    Render a simple header action button.

    Args:
        icon: Ionicon name
        alpine_click: Alpine.js @click handler
        onclick: JavaScript onclick handler
        color: Button color
        css_class: Additional CSS classes
    """
    attrs = []
    if alpine_click:
        attrs.append(f'@click="{alpine_click}"')
    if onclick:
        attrs.append(f'onclick="{onclick}"')
    if color:
        attrs.append(f'color="{color}"')
    if css_class:
        attrs.append(f'class="{css_class}"')

    attrs_str = ' '.join(attrs)
    return mark_safe(f'<ion-button {attrs_str}><ion-icon slot="icon-only" name="{icon}"></ion-icon></ion-button>')


# =============================================================================
# SIDEBAR COMPONENTS
# =============================================================================

@register.inclusion_tag("ui/sidebar_header.html")
def ui_sidebar_header(logo_src=None, logo_static=None, logo_alt="Logo", logo_text=None, css_class=""):
    """
    Render sidebar header with logo.

    Args:
        logo_src: Logo image URL (absolute)
        logo_static: Logo static path (relative to static folder)
        logo_alt: Logo alt text
        logo_text: Text next to logo
    """
    return {
        "logo_src": logo_src,
        "logo_static": logo_static,
        "logo_alt": logo_alt,
        "logo_text": logo_text,
        "css_class": css_class,
    }


@register.inclusion_tag("ui/sidebar_footer.html")
def ui_sidebar_footer(signout_url=None, signout_label="Sign Out", css_class=""):
    """
    Render sidebar footer with sign out button.

    Args:
        signout_url: Sign out URL
        signout_label: Sign out button label
    """
    return {
        "signout_url": signout_url,
        "signout_label": signout_label,
        "css_class": css_class,
    }


class SidebarNavNode(BlockTagNode):
    """{% ui_sidebar_nav %}...{% endui_sidebar_nav %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)
        css_class = kwargs.get('css_class', '')

        class_attr = f' class="sidebar-menu {css_class}"' if css_class else ' class="sidebar-menu"'

        return f'<nav id="sidebar-nav"{class_attr}><ion-list id="sidebar-nav-list">{content}</ion-list></nav>'


@register.tag('ui_sidebar_nav')
def do_ui_sidebar_nav(parser, token):
    """
    Block tag for sidebar navigation list.

    Usage:
        {% ui_sidebar_nav %}
            {% ui_nav_item label="Dashboard" icon="grid-outline" %}
        {% endui_sidebar_nav %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_sidebar_nav',))
    parser.delete_first_token()
    return SidebarNavNode(nodelist, args, kwargs)


class SidebarContentNode(BlockTagNode):
    """{% ui_sidebar_content %}...{% endui_sidebar_content %}"""

    def render(self, context):
        content = self.nodelist.render(context)
        return f'<ion-content id="sidebar-content"><div id="sidebar-wrapper" class="sidebar-wrapper">{content}</div></ion-content>'


@register.tag('ui_sidebar_content')
def do_ui_sidebar_content(parser, token):
    """
    Block tag for sidebar content wrapper.

    Usage:
        {% ui_sidebar_content %}
            {% ui_sidebar_header %}
            {% ui_sidebar_nav %}...{% endui_sidebar_nav %}
            {% ui_sidebar_footer %}
        {% endui_sidebar_content %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_sidebar_content',))
    parser.delete_first_token()
    return SidebarContentNode(nodelist, args, kwargs)


class AccordionGroupNode(BlockTagNode):
    """{% ui_accordion_group %}...{% endui_accordion_group %}"""

    def render(self, context):
        content = self.nodelist.render(context)
        return f'<ion-accordion-group>{content}</ion-accordion-group>'


@register.tag('ui_accordion_group')
def do_ui_accordion_group(parser, token):
    """
    Block tag for accordion group.

    Usage:
        {% ui_accordion_group %}
            {% ui_accordion header_label="Section" %}
                content
            {% endui_accordion %}
        {% endui_accordion_group %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_accordion_group',))
    parser.delete_first_token()
    return AccordionGroupNode(nodelist, args, kwargs)


class AccordionNode(BlockTagNode):
    """{% ui_accordion header_label="..." header_icon="..." %}...{% endui_accordion %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)

        header_label = kwargs.get('header_label', '')
        header_icon = kwargs.get('header_icon', '')
        css_class = kwargs.get('css_class', '')

        html = '<ion-accordion>'
        html += f'<ion-item slot="header" class="nav-item{" " + css_class if css_class else ""}">'
        if header_icon:
            html += f'<ion-icon name="{header_icon}" slot="start"></ion-icon>'
        html += f'<ion-label>{header_label}</ion-label>'
        html += '</ion-item>'
        html += f'<div slot="content" class="submenu-content">{content}</div>'
        html += '</ion-accordion>'

        return html


@register.tag('ui_accordion')
def do_ui_accordion(parser, token):
    """
    Block tag for accordion item.

    Usage:
        {% ui_accordion header_label="Settings" header_icon="settings-outline" %}
            {% ui_nav_item label="General" %}
        {% endui_accordion %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_accordion',))
    parser.delete_first_token()
    return AccordionNode(nodelist, args, kwargs)


@register.inclusion_tag("ui/submenu_item.html")
def ui_submenu_item(
    label,
    icon=None,
    url=None,
    hx_get=None,
    hx_target=None,
    hx_push_url=True,
    active=False,
    css_class="",
    **kwargs
):
    """
    Render a submenu item (for accordion content).

    Args:
        label: Item text
        icon: Ionicon name
        url: Navigation URL
        hx_get: HTMX URL
        hx_target: HTMX target
        hx_push_url: Push URL to history
        active: Is current item active
    """
    return {
        "label": label,
        "icon": icon,
        "url": url,
        "hx_get": hx_get,
        "hx_target": hx_target,
        "hx_push_url": hx_push_url,
        "active": active,
        "css_class": css_class,
        "extra_attrs": kwargs,
    }


@register.inclusion_tag("ui/empty_nav_item.html")
def ui_empty_nav_item(label, icon="information-circle-outline", css_class=""):
    """
    Render an empty/informational nav item (non-clickable).

    Args:
        label: Item text
        icon: Ionicon name
    """
    return {
        "label": label,
        "icon": icon,
        "css_class": css_class,
    }


# =============================================================================
# HTMX COMPONENTS
# =============================================================================

@register.inclusion_tag("ui/toast_oob.html")
def ui_toast_oob(message, color="primary", duration=2000):
    """
    Render a toast notification via HTMX Out-of-Band swap.

    Include this in HTMX responses to show a toast without JavaScript.

    Args:
        message: Toast message
        color: success, danger, warning, primary
        duration: Duration in milliseconds (default: 2000)
    """
    return {
        "message": message,
        "color": color,
        "duration": duration,
    }


# =============================================================================
# TEXT FILTERS
# =============================================================================

@register.filter(name='markdown')
def markdown_filter(text):
    """
    Convert markdown text to HTML.

    Usage:
        {{ module.readme|markdown }}
    """
    import markdown as md

    if not text:
        return ''

    # Configure markdown with common extensions
    html = md.markdown(
        text,
        extensions=[
            'markdown.extensions.fenced_code',  # ```code blocks```
            'markdown.extensions.tables',        # tables support
            'markdown.extensions.nl2br',         # newline to <br>
            'markdown.extensions.sane_lists',    # better list handling
        ]
    )

    return mark_safe(html)


# =============================================================================
# MODULE GRID COMPONENTS (iOS-style app launcher)
# =============================================================================

@register.inclusion_tag("ui/module_app_icon.html")
def ui_module_app_icon(
    module_id,
    label,
    icon="cube-outline",
    url=None,
    color="primary",
    badge=None,
    badge_color="danger",
    is_favorite=False,
    icon_svg=None,
    css_class="",
):
    """
    Render an iOS-style app icon for the module grid.

    Args:
        module_id: Unique identifier for the module
        label: Display name
        icon: Ionicon name (e.g., "cube-outline")
        url: Navigation URL
        color: Background color (primary, success, warning, danger, medium, etc.)
        badge: Badge text (e.g., notification count)
        badge_color: Badge color
        is_favorite: Show star indicator
        icon_svg: Optional SVG content for custom icons
    """
    return {
        "module_id": module_id,
        "label": label,
        "icon": icon,
        "url": url,
        "color": color,
        "badge": badge,
        "badge_color": badge_color,
        "is_favorite": is_favorite,
        "icon_svg": icon_svg,
        "css_class": css_class,
    }


class ModuleSectionNode(BlockTagNode):
    """{% ui_module_section title="..." %}...{% endui_module_section %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)

        title = kwargs.get('title', '')
        icon = kwargs.get('icon', '')
        action_label = kwargs.get('action_label', '')
        action_url = kwargs.get('action_url', '')
        action_hx_get = kwargs.get('action_hx_get', '')
        css_class = kwargs.get('css_class', '')

        # Build section HTML
        html = f'<div class="module-section{" " + css_class if css_class else ""}">'
        html += '<div class="module-section__header">'

        if icon:
            html += f'<ion-icon name="{icon}" class="module-section__icon"></ion-icon>'

        html += f'<h3 class="module-section__title">{title}</h3>'

        if action_label:
            if action_hx_get:
                html += f'<ion-button fill="clear" size="small" hx-get="{action_hx_get}" hx-target="#main-content-area" hx-push-url="true">{action_label}</ion-button>'
            elif action_url:
                html += f'<ion-button fill="clear" size="small" href="{action_url}">{action_label}</ion-button>'

        html += '</div>'
        html += f'<div class="module-grid">{content}</div>'
        html += '</div>'

        return html


@register.tag('ui_module_section')
def do_ui_module_section(parser, token):
    """
    Block tag for module section with title and grid.

    Usage:
        {% ui_module_section title="Favorites" icon="star" %}
            {% ui_module_app_icon ... %}
        {% endui_module_section %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_module_section',))
    parser.delete_first_token()
    return ModuleSectionNode(nodelist, args, kwargs)


class ModuleGridNode(BlockTagNode):
    """{% ui_module_grid %}...{% endui_module_grid %}"""

    def render(self, context):
        args, kwargs = self.resolve_args(context)
        content = self.nodelist.render(context)
        css_class = kwargs.get('css_class', '')

        class_attr = f'module-grid{" " + css_class if css_class else ""}'
        return f'<div class="{class_attr}">{content}</div>'


@register.tag('ui_module_grid')
def do_ui_module_grid(parser, token):
    """
    Block tag for module grid container.

    Usage:
        {% ui_module_grid %}
            {% ui_module_app_icon ... %}
        {% endui_module_grid %}
    """
    tag_name, args, kwargs = parse_token_args(parser, token)
    nodelist = parser.parse(('endui_module_grid',))
    parser.delete_first_token()
    return ModuleGridNode(nodelist, args, kwargs)


# =============================================================================
# TAB BAR COMPONENT
# =============================================================================

@register.inclusion_tag('ui/tabbar.html', takes_context=True)
def ui_tabbar(context, tabs=None, current_view=None):
    """
    Renders an ion-tab-bar with the given tabs.

    Usage:
        {% ui_tabbar tabs=module_tabs current_view=current_view %}

    Where tabs is a list of dicts:
        [
            {"url": "inventory:dashboard", "icon": "grid-outline", "label": "Overview", "view": "dashboard"},
            {"url": "inventory:products", "icon": "cube-outline", "label": "Products", "view": "products"},
            {"url": "inventory:settings", "icon": "settings-outline", "label": "Settings", "view": "settings", "disabled": False},
        ]

    Each tab dict can have:
        - url: Django URL name (required) - will be resolved with {% url %}
        - icon: Ionicon name (required)
        - label: Tab label text (required)
        - view: View identifier to match current_view for active state (optional)
        - disabled: If True, tab is disabled (optional)
        - badge: Badge text to show (optional)
        - badge_color: Badge color (optional, default: "danger")
    """
    return {
        'tabs': tabs or [],
        'current_view': current_view or '',
        'request': context.get('request'),
    }


@register.simple_tag(takes_context=True)
def ui_tabbar_oob(context, tabs=None, current_view=None):
    """
    Renders an ion-tab-bar with OOB swap for HTMX navigation.

    Usage in content partials:
        {% if request.htmx %}
        {% ui_tabbar_oob tabs=module_tabs current_view=current_view %}
        {% endif %}

    This renders the tabbar wrapped in an OOB swap div for HTMX updates.
    """
    from django.template.loader import render_to_string

    html = render_to_string('ui/tabbar_oob.html', {
        'tabs': tabs or [],
        'current_view': current_view or '',
        'request': context.get('request'),
    }, request=context.get('request'))

    return mark_safe(html)


@register.inclusion_tag('ui/tab.html', takes_context=True)
def ui_tab(context, url, icon, label, active=False, disabled=False, badge=None, badge_color='danger'):
    """
    Renders a single ion-tab-button for use in module layouts.

    Usage:
        {% ui_tab url="inventory:dashboard" icon="grid-outline" label=_("Overview") active=True %}
        {% ui_tab url="inventory:products" icon="cube-outline" label=_("Products") %}
        {% ui_tab url="inventory:settings" icon="settings-outline" label=_("Settings") disabled=True %}
        {% ui_tab url="marketplace:cart" icon="cart-outline" label=_("Cart") badge=cart_count badge_color="danger" %}

    Args:
        url: Django URL name (required) - will be resolved with {% url %}
        icon: Ionicon name (required)
        label: Tab label text (required) - use _("text") for translation
        active: If True, tab is marked as selected (optional)
        disabled: If True, tab is disabled (optional)
        badge: Badge text to show (optional)
        badge_color: Badge color (optional, default: "danger")
    """
    return {
        'url': url,
        'icon': icon,
        'label': label,
        'active': active,
        'disabled': disabled,
        'badge': badge,
        'badge_color': badge_color,
        'request': context.get('request'),
    }

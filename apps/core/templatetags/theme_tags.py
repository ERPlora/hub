"""
Template tags para el sistema de temas.
"""
from django import template
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def theme_logo(theme_name='default'):
    """
    Retorna la URL del logo para el tema especificado.

    Usage:
        {% load theme_tags %}
        <img src="{% theme_logo hub_config.color_theme %}" alt="Logo">
    """
    return static(f'css/themes/{theme_name}/erplorer-logo.svg')


@register.simple_tag
def theme_css(theme_name='default'):
    """
    Retorna la URL del CSS del tema especificado.

    Usage:
        {% load theme_tags %}
        <link rel="stylesheet" href="{% theme_css hub_config.color_theme %}">
    """
    return static(f'css/themes/{theme_name}/ionic-theme.css')

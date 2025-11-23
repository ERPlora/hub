"""
Context processors for core app
"""
from django.conf import settings


def cloud_url(request):
    """
    Add CLOUD_URL to template context
    """
    return {
        'CLOUD_URL': settings.CLOUD_API_URL
    }


def plugin_menu_items(request):
    """
    Add plugin menu items to template context
    """
    from apps.plugins_runtime.loader import plugin_loader

    # Only load plugins if user is authenticated
    if 'local_user_id' in request.session:
        menu_items = plugin_loader.get_menu_items()
    else:
        menu_items = []

    return {
        'PLUGIN_MENU_ITEMS': menu_items
    }


def hub_config_context(request):
    """
    Add hub_config and store_config to template context.

    This makes both HubConfig (language, currency, theme) and StoreConfig
    (business data) available in all templates without having to explicitly
    pass them in each view.
    """
    from apps.configuration.models import HubConfig, StoreConfig

    return {
        'hub_config': HubConfig.get_config(),
        'store_config': StoreConfig.get_config()
    }

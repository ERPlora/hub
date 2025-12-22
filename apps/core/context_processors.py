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


def module_menu_items(request):
    """
    Add module menu items to template context
    """
    from apps.modules_runtime.loader import module_loader

    # Only load modules if user is authenticated
    if 'local_user_id' in request.session:
        menu_items = module_loader.get_menu_items()
    else:
        menu_items = []

    return {
        'MODULE_MENU_ITEMS': menu_items
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


def deployment_config(request):
    """
    Expose deployment configuration to templates.

    Makes DEPLOYMENT_MODE and related settings available in templates:
    - {{ DEPLOYMENT_MODE }} - 'local' or 'web'
    - {{ IS_LOCAL_DEPLOYMENT }} - True if local (desktop app)
    - {{ IS_WEB_DEPLOYMENT }} - True if web (browser)
    - {{ LOCAL_PRINT_SERVICE_URL }} - URL for local print service
    """
    deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'local')

    return {
        'DEPLOYMENT_MODE': deployment_mode,
        'IS_LOCAL_DEPLOYMENT': deployment_mode == 'local',
        'IS_WEB_DEPLOYMENT': deployment_mode == 'web',
        'LOCAL_PRINT_SERVICE_URL': getattr(settings, 'LOCAL_PRINT_SERVICE_URL', 'http://localhost:8080'),
    }

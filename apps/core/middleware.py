from django.utils import translation
from django.shortcuts import redirect
from django.urls import reverse
from .models import HubConfig, StoreConfig
from .utils import detect_os_language


class LanguageMiddleware:
    """
    Custom language middleware that:
    1. Uses OS language for login page (before authentication)
    2. Uses user's preferred language after login
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is logged in
        local_user_id = request.session.get('local_user_id')

        if local_user_id:
            # User is logged in - use user's language preference
            user_language = request.session.get('user_language', 'en')
            translation.activate(user_language)
            request.LANGUAGE_CODE = user_language
        else:
            # User not logged in - use OS language
            hub_config = HubConfig.get_config()

            # Detect and save OS language on first run
            if not hub_config.os_language or hub_config.os_language == 'en':
                os_lang = detect_os_language()
                if os_lang != hub_config.os_language:
                    hub_config.os_language = os_lang
                    hub_config.save()

            # Activate OS language
            translation.activate(hub_config.os_language)
            request.LANGUAGE_CODE = hub_config.os_language

        response = self.get_response(request)

        # Deactivate to prevent leaking to other requests
        translation.deactivate()

        return response


class StoreConfigCheckMiddleware:
    """
    Middleware to check if store is configured after login.
    If store is not configured, redirect to settings page.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require store configuration
        self.exempt_paths = [
            reverse('core:login'),
            reverse('core:logout'),
            reverse('core:settings'),
            '/api/',  # API endpoints
            '/static/',  # Static files
            '/media/',  # Media files
        ]

    def __call__(self, request):
        # Check if user is logged in
        if 'local_user_id' in request.session:
            # Check if current path is exempt
            path = request.path
            is_exempt = any(path.startswith(exempt) for exempt in self.exempt_paths)

            if not is_exempt:
                # Check if store configuration check has been done in this session
                if not request.session.get('store_config_checked', False):
                    store_config = StoreConfig.get_config()

                    # If store is not configured, redirect to settings
                    if not store_config.is_complete():
                        request.session['store_config_checked'] = True
                        request.session['settings_message'] = 'Please complete store configuration to continue'
                        return redirect('core:settings')

                    # Mark as checked for this session
                    request.session['store_config_checked'] = True

        response = self.get_response(request)
        return response

from django.utils import translation
from apps.configuration.models import HubConfig
from ..utils import detect_os_language


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

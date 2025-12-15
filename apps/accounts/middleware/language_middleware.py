from django.utils import translation
from django.conf import settings
from apps.configuration.models import HubConfig
from apps.core.utils import detect_os_language


class LanguageMiddleware:
    """
    Custom language middleware that:
    1. Uses cookie language (set by browser auto-detection)
    2. Uses user's preferred language after login (from session)
    3. Falls back to OS language for login page (before authentication)
    4. Falls back to default language code
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = None

        # Priority 1: Check session language (logged-in user preference)
        local_user_id = request.session.get('local_user_id')
        if local_user_id:
            language = request.session.get('user_language')

        # Priority 2: Check cookie (browser auto-detected language)
        if not language:
            cookie_name = getattr(settings, 'LANGUAGE_COOKIE_NAME', 'django_language')
            language = request.COOKIES.get(cookie_name)

        # Priority 3: Check session cookie key (alternative session storage)
        if not language:
            language = request.session.get(getattr(settings, 'LANGUAGE_COOKIE_NAME', 'django_language'))

        # Priority 4: Use OS detected language (for login page)
        if not language:
            hub_config = HubConfig.get_config()

            # Detect and save OS language on first run
            if not hub_config.os_language or hub_config.os_language == 'en':
                os_lang = detect_os_language()
                if os_lang != hub_config.os_language:
                    hub_config.os_language = os_lang
                    hub_config.save()

            language = hub_config.os_language

        # Priority 5: Fallback to default
        if not language:
            language = settings.LANGUAGE_CODE

        # Validate language is supported
        supported_languages = [code for code, name in settings.LANGUAGES]
        if language not in supported_languages:
            language = settings.LANGUAGE_CODE

        # Activate the determined language
        translation.activate(language)
        request.LANGUAGE_CODE = language

        response = self.get_response(request)

        # Deactivate to prevent leaking to other requests
        translation.deactivate()

        return response

"""The language a person chooses for themselves, left on the answer of the request that chose it.

Django speaks the language of its cookie (``LocaleMiddleware``), and only an answer can leave a cookie, while
``base.profile.preferences_set`` runs from «My profile», from the assistant's card or from the API. So the operation
marks its request (:func:`choose`) and :class:`ChosenLanguageMiddleware` leaves the cookie on that request's answer,
whichever door it was, as Django's CSRF middleware does with a token a view asked for. An error leaves nothing.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

CHOSEN_LANGUAGE_ATTR = "hub_chosen_language"


def choose(request: HttpRequest | None, language: str) -> None:
    """The answer to ``request`` leaves ``language`` as the person's; without a request (a job) there is no answer."""
    if request is not None:
        setattr(request, CHOSEN_LANGUAGE_ATTR, language)


class ChosenLanguageMiddleware(MiddlewareMixin):
    def process_response(self, request: HttpRequest, response: HttpResponseBase) -> HttpResponseBase:
        # An error undid what the request changed: the person's language is still the one before.
        if response.status_code < 400:
            with_language_cookie(response, getattr(request, CHOSEN_LANGUAGE_ATTR, ""))
        return response


def with_language_cookie(response: HttpResponseBase, language: str) -> None:
    """Leave Django's language cookie of ``language`` on ``response`` (the login's, «My profile»'s preferences)."""
    if supported_language(language) is not None:
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )


def supported_language(locale: str) -> str | None:
    try:
        return translation.get_supported_language_variant(locale) if locale else None
    except LookupError:
        return None

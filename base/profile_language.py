"""The language a signed-in person chose in «My profile», spoken on every device they are signed in on.

Django speaks the language of the browser's cookie (``LocaleMiddleware``), and only the device that chose a language
gets the new cookie (``base.chosen_language``): another device of the same person, signed in before, would go on in
the language from before, also after reloading. So each request of a signed-in person in a business speaks the
language kept in their profile, as Django's documentation suggests for a language stored with the user. Without a
choice of their own, the cookie their way in left stands: the business's with a PIN, their account's with it.
"""

from django.http import HttpRequest, HttpResponseBase
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

from base import queries
from base.chosen_language import supported_language
from base.middleware import HubDatabaseMiddleware
from base.tenancy.limits import HubBusy


class ProfileLanguageMiddleware(MiddlewareMixin):
    """Placed right after ``SessionHostMiddleware``: in a business, with the person's session already checked."""

    def process_request(self, request: HttpRequest) -> HttpResponseBase | None:
        if getattr(request, "hub", None) is None or not request.user.is_authenticated:
            return None
        try:
            language = supported_language(queries.profile.chosen_language(request.user))
        except HubBusy as busy:
            # It reads the business's database before any view, and what it raises never reaches
            # HubDatabaseMiddleware.process_exception: the same 503 the view would have answered.
            return HubDatabaseMiddleware._busy(request, busy)
        if language is not None:
            translation.activate(language)
            request.LANGUAGE_CODE = language
        return None

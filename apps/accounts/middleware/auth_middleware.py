"""
Hub Authentication Middleware

Attaches LocalUser instance to request.user based on session data.
This replaces Django's default AnonymousUser with the authenticated LocalUser.
"""

from django.utils.functional import SimpleLazyObject
from apps.accounts.models import LocalUser


class AnonymousUser:
    """
    Anonymous user for unauthenticated requests.
    Compatible with Django's authentication system.
    """
    id = None
    pk = None
    username = ''
    is_staff = False
    is_active = False
    is_superuser = False
    is_authenticated = False

    def __str__(self):
        return 'AnonymousUser'

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __hash__(self):
        return 1

    def save(self):
        raise NotImplementedError("Django doesn't provide a DB representation for AnonymousUser.")

    def delete(self):
        raise NotImplementedError("Django doesn't provide a DB representation for AnonymousUser.")

    def set_password(self, raw_password):
        raise NotImplementedError("Django doesn't provide a DB representation for AnonymousUser.")

    def check_password(self, raw_password):
        raise NotImplementedError("Django doesn't provide a DB representation for AnonymousUser.")


def get_user(request):
    """
    Get LocalUser from session.
    Returns LocalUser instance if authenticated, AnonymousUser otherwise.
    """
    local_user_id = request.session.get('local_user_id')
    if not local_user_id:
        return AnonymousUser()

    try:
        return LocalUser.objects.get(id=local_user_id, is_active=True)
    except LocalUser.DoesNotExist:
        # User was deleted or deactivated, clear session
        request.session.flush()
        return AnonymousUser()


class LocalUserAuthenticationMiddleware:
    """
    Middleware that attaches LocalUser to request.user.

    Must be placed after SessionMiddleware in settings.MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Attach user to request (lazy loaded)
        request.user = SimpleLazyObject(lambda: get_user(request))

        # Add helper property to check if user is authenticated
        request.user_authenticated = 'local_user_id' in request.session

        response = self.get_response(request)
        return response

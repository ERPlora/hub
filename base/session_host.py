"""``SessionHostMiddleware``: a session is a session of the host it was opened on (the login notes it);
on another hub's host, or on the platform host, it is anonymous (401).
"""

from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin

#: Where the login noted the host a session was opened on: a hub's slug, or :data:`PLATFORM_SESSION_HOST`.
SESSION_HOST_KEY = "hub_host"
#: The platform host's mark (no hub's slug can be it: ``live.slugs``).
PLATFORM_SESSION_HOST = "@platform"


def session_host(request: HttpRequest) -> str | None:
    """The host a session of this request belongs to: the hub's slug, the platform host's mark, or ``None``."""
    if getattr(request, "platform_host", False):
        return PLATFORM_SESSION_HOST
    hub = getattr(request, "hub", None)
    return hub.slug if hub is not None else None


def opened_elsewhere(request: HttpRequest) -> bool:
    """Whether the request's session was opened on another host than the request's (a hub's or the platform's).

    The one rule of every way in that reads a session: ``SessionHostMiddleware`` and the print socket
    (``base.ws_print``). A session with no host noted (from before the rule) is not.
    """
    host = session_host(request)
    if host is None:
        return False
    noted = request.session.get(SESSION_HOST_KEY)
    return noted is not None and noted != host


@receiver(user_logged_in)
def note_the_sessions_host(sender, request, user, **kwargs) -> None:
    """Every login notes its host in the new session (the SaaS's jump, a demo's, the admin's)."""
    host = session_host(request) if request is not None else None
    if host is not None and hasattr(request, "session"):
        request.session[SESSION_HOST_KEY] = host


class SessionHostMiddleware(MiddlewareMixin):
    """Placed right after ``AuthenticationMiddleware``: a session opened on another host is no session here.

    Sessions live in control's database: a session of hub B would otherwise be
    valid on A's host for a user who is a member of both. Here it is anonymous (401 on the API; on a page, the
    SaaS's login, as without a session). A session from before this rule, with no host noted, stays valid until it
    expires; ``/internal`` and the open paths, with no hub, are left alone.
    """

    def process_request(self, request: HttpRequest) -> None:
        if opened_elsewhere(request):
            request.user = AnonymousUser()

            async def anonymous():
                return request.user

            request.auser = anonymous

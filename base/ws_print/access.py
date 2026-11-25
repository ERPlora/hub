"""Who the print channel acts as: the session's user, checked at every frame and counted when it is refused, and
the context printing's operations run with."""

import math
from importlib import import_module

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.models import AnonymousUser
from django.utils.translation import gettext, ngettext
from live.context import OperationContext, get_builder
from live.errors import OperationError

from base import session_host
from base.throttle import AttemptLimit, RateLimited, client_key
from base.ws_print.printing import _operation, _validated
from base.ws_print.refusals import Refusal, _refusal_of

#: Sessions refused per caller (one that is not valid here, or ended): 10 within 5 minutes of the first (README,
#: «Límites de intentos»). A ``hello`` with no session tried nothing and is not counted.
SESSION_ATTEMPTS = AttemptLimit("ws_print", attempts=10, window=300)


class AccessMixin:
    """The session and the context of a ``PrintSocket`` (``base.ws_print.protocol``), which keeps the request and
    the device."""

    def _authenticate(self):
        """The session's user; refused when there is none, it is not valid here or it is not the ``hello``'s."""
        key = self.request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        if not key:
            raise Refusal("unauthenticated", gettext("Sign in to this hub to print: this connection has no session."), status=401)
        self.request.session = import_module(settings.SESSION_ENGINE).SessionStore(key)
        # A session opened on another host is no session here: the HTTP doors' rule.
        user = AnonymousUser() if session_host.opened_elsewhere(self.request) else auth.get_user(self.request)
        held = self.device.ctx.actor if self.device is not None else None
        if not user.is_authenticated or (held is not None and user.pk != held.pk):
            self._count_refused_session()
            raise Refusal(
                "unauthenticated",
                gettext("This connection's session is not valid on this hub: sign in again."),
                status=401,
            )
        return user

    def _count_refused_session(self) -> None:
        """One more refused session of this caller; a ``Refusal`` 429 when it is already past :data:`SESSION_ATTEMPTS`."""
        caller = client_key(self.request)
        wait = SESSION_ATTEMPTS.wait(caller)
        if wait:
            minutes = math.ceil(wait / 60)
            message = ngettext(
                "Too many failed sign-ins from this connection. Try again in %(minutes)s minute.",
                "Too many failed sign-ins from this connection. Try again in %(minutes)s minutes.",
                minutes,
            ) % {"minutes": minutes}
            raise Refusal(RateLimited.code, message, status=RateLimited.status)
        SESSION_ATTEMPTS.failed(caller)

    def _fresh_context(self) -> OperationContext:
        """The ``hello``'s context with its permissions read again, as the live executor does before every run."""
        self.device.ctx = get_builder().refresh(self.device.ctx)
        return self.device.ctx

    def _run(self, name: str, data: dict) -> dict:
        """Run printing's operation ``name`` as the device's user (its session was checked for the frame)."""
        op = _operation(name)
        try:
            return op(self._fresh_context(), _validated(name, data)).model_dump(mode="json")
        except OperationError as exc:
            refusal = _refusal_of(exc)
            if refusal.fatal:
                raise refusal from exc
            raise

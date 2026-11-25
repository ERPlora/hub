"""Whoever books without an account: what the public operations may do for her in the other apps, and what is kept of
her, a fingerprint of her address and the hash of her link."""

import hashlib
import hmac
from dataclasses import replace

from django.conf import settings as django_settings
from live.context import OperationContext

PUBLIC = "online_booking.public"
#: Who books when nobody is signed in (the appointment's «created by»; its history says «the customer»).
ONLINE_ACTOR = "online booking"
#: What the public operations need of the other apps, and nothing else: read the agenda and the free times,
#: book and cancel in it, find or create the customer's card, read the catalog, the hours and the team.
DELEGATED = frozenset(
    {
        "appointment.view_appointment",
        "appointment.view_own_appointment",
        "appointment.add_appointment",
        "appointment.add_own_appointment",
        "appointment.change_appointment",
        "appointment.change_own_appointment",
        "appointment.view_schedule",
        "customer.view",
        "customer.manage",
        "service.view_service",
        "schedule.view",
        "staff.view",
    }
)


def delegated(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to do in the other apps what a public operation needs (and only that)."""
    actor = ctx.actor if ctx.actor is not None else ONLINE_ACTOR
    return replace(ctx, actor=actor, permissions=ctx.permissions | DELEGATED)


def hash_token(token: str) -> str:
    """What is kept of the customer's link: its SHA-256, never the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()


def _client_address(request) -> str:
    """The visitor's address: the last hop of ``X-Forwarded-For`` (the one the load balancer adds), or the
    socket's when there is no proxy."""
    hops = [
        hop.strip()
        for hop in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if hop.strip()
    ]
    return hops[-1] if hops else request.META.get("REMOTE_ADDR", "")


def visitor_key(ctx: OperationContext) -> str:
    """A fingerprint of who books (HMAC of the address with the secret key): the limits count it, the address
    itself is never kept. Without a request, the actor stands for the visitor."""
    address = _client_address(ctx.request) if ctx.request is not None else ""
    source = address or f"actor:{getattr(ctx.actor, 'pk', ctx.actor)}"
    return hmac.new(
        django_settings.SECRET_KEY.encode(), source.encode(), hashlib.sha256
    ).hexdigest()

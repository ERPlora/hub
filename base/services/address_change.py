"""What control keeps under a business's web address, when the business takes another one."""

from functools import partial

from live.operations import on_commit

from base import activation
from base.models import Hub, Membership
from base.models.sessions import SessionOwner
from base.services.sessions import _end_sessions
from control.models import HubVisit


def forget_address(address: str) -> None:
    """Nothing is left at ``address``, which a business is about to take: whoever had it before left nothing there."""
    _end_sessions(SessionOwner.objects.filter(host=address))
    Membership.objects.filter(host=address).delete()
    HubVisit.objects.filter(host=address).delete()
    on_commit(partial(activation.forget, address))


def address_changed(hub: Hub, former: str) -> None:
    """``hub``, at ``hub.slug`` from now on, leaves ``former``, in the transaction that says so: its people and who came
    in go with it. The sessions opened there end, as a browser keeps each one for its own address."""
    if hub.slug == former:
        return
    forget_address(hub.slug)
    Membership.objects.filter(host=former).update(host=hub.slug)
    HubVisit.objects.filter(host=former).update(host=hub.slug)
    forget_address(former)

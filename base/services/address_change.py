"""What is kept under a business's web address, when the business takes another one."""

from functools import partial
from uuid import uuid7

from live.operations import atomic, on_commit

from base import activation, registry
from base.models import Hub, Membership
from base.models.activation import AppActivation
from base.models.sessions import SessionOwner
from base.services.sessions import _end_sessions
from control.models import HubVisit


def forget_address(address: str) -> None:
    """Nothing is left in control at ``address``: of whoever had it before, or of the business that leaves it."""
    _end_sessions(SessionOwner.objects.filter(host=address))
    Membership.objects.filter(host=address).delete()
    HubVisit.objects.filter(host=address).delete()
    on_commit(partial(activation.forget, address))


def address_changed(hub: Hub, former: str) -> None:
    """``hub``, at ``hub.slug`` from now on, leaves ``former``, in the transaction that says so: its people, who came in
    and its apps go with it. The sessions opened there end, as a browser keeps each one for its own address."""
    if hub.slug == former:
        return
    forget_address(hub.slug)
    Membership.objects.filter(host=former).update(host=hub.slug)
    HubVisit.objects.filter(host=former).update(host=hub.slug)
    forget_address(former)
    if registry.database_is_made(hub):
        _bring_apps(hub, former)


def _bring_apps(hub: Hub, former: str) -> None:
    """Write down in ``hub``'s own database, under the address it takes, its apps as they are under ``former``, instead
    of whatever another business left there.

    That database commits before control, and those under ``former`` stay: if control never says the business moved, it
    goes on where it was, and erplora.com asks again."""
    from base.tenancy.context import use_hub

    with use_hub(hub), atomic():
        apps = list(AppActivation.objects.select_for_update().filter(host=former))
        if not apps:
            return
        AppActivation.objects.filter(host=hub.slug).delete()
        for app in apps:
            app.pk, app.host = uuid7(), hub.slug
        AppActivation.objects.bulk_create(apps)

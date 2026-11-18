"""VeriFactu is only for businesses in Spain: the country erplora.com registered for the business."""

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope, system_context
from live.errors import AppInactive, NotFound
from live.operations import get as get_operation

from base.business import country_or_market
from apps.verifactu.apps import SPAIN

#: The wait of every record of a business outside Spain: none of them is ever sent.
OUTSIDE_SPAIN = "outside_spain"
ONLY_IN_SPAIN = _("VeriFactu is only for businesses in Spain.")
#: What tells the business's country: this hub's registry, as erplora.com wrote it, never asking erplora.com.
BUSINESS = "base.business.get"


def business_country(scope: Scope | None) -> str:
    """The country erplora.com registered for ``scope``'s business (ISO 3166-1 alpha-2), as ``base.business.get`` reads
    it, as the platform (an API key holds only the permission of the operation it opened). ERPlora's own hub too: the
    platform answers its business (its issuer's country), so VeriFactu keeps no second source of it. ``""`` when there
    is none: a demo, or a scope that is no business's (no registry row), both in ERPlora's market, Spain."""
    if scope is None:
        return ""
    business = get_operation(BUSINESS)
    try:
        return business(system_context(scope), business.input()).country
    except NotFound:
        return ""


def outside_spain(scope: Scope | None) -> bool:
    """Whether ``scope``'s business was registered in a country other than Spain: VeriFactu is not for it, so nothing of
    it is sealed nor sent, as if the app were off. One without a country is in ERPlora's market, Spain: base's one
    reading of it (``base.business.country_or_market``)."""
    return country_or_market(business_country(scope)) != SPAIN


def refuse_outside_spain(ctx: OperationContext) -> None:
    """What seals a record or reaches the AEAT refuses a business outside Spain as an app that is off: 404
    ``app_inactive`` with the reason, in ``ctx``'s language, before it reads or writes anything (so an invoice of
    Invoicing is issued without a record, «unavailable», never undone)."""
    if outside_spain(ctx.scope):
        with translation.override(ctx.language):
            raise AppInactive(str(ONLY_IN_SPAIN))

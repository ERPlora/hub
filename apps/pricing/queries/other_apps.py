"""Services, by the name of its operations (Services is no requirement): the service a price or a rule names, and
the one a recovery made again.
"""

from uuid import UUID

import pydantic
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, system_context
from live.errors import AppInactive, Conflict, InvalidPayload
from live.operations import UnknownOperation, get

from base import operations as platform

SERVICES_UNAVAILABLE = _("Services is not active in this business.")

SERVICE_GET = "service.service.get"
SERVICE_STANDING_FOR = "service.service.standing_for"


def call_service(ctx: OperationContext, service_id: UUID | None, said: str | None):
    """Services' ``service.service.get`` for the caller (its permission applies): a ``ServiceOut``.

    Services off or absent → 409 ``pricing.services_unavailable``; its own refusals (a service that does
    not exist, a name that matches several) reach the caller as they are."""
    unavailable = Conflict(str(SERVICES_UNAVAILABLE), code="pricing.services_unavailable")
    try:
        op = get(SERVICE_GET)
    except UnknownOperation:
        raise unavailable from None
    data = {"id": str(service_id)} if service_id is not None else {"service": said}
    try:
        payload = op.input.model_validate(data)
    except pydantic.ValidationError as invalid:
        fields = {"service": error["msg"] for error in invalid.errors()}
        raise InvalidPayload(next(iter(fields.values())), code="invalid_field", fields=fields) from None
    try:
        return op(ctx, payload)
    except AppInactive:
        raise unavailable from None


def services_standing_for(ids: set[UUID]) -> dict[UUID, UUID]:
    """Services' ``service.service.standing_for``, asked as the platform in the business at work: the service a
    recovery made again for each of a separate copy's ``ids`` the business no longer holds, ``{id there: id here}``.
    With Services off or absent, none: each price keeps the copy's service, and the list detail's add says why."""
    if not ids:
        return {}
    try:
        op = get(SERVICE_STANDING_FOR)
        return op(system_context(platform.current_business_scope()), op.input(ids=sorted(ids))).standing_for
    except (UnknownOperation, AppInactive):
        return {}

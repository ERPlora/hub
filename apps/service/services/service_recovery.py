"""A service the business no longer has, made again from a separate copy (BASE-F114), with the professionals who perform
it that Staff still has.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.service.models.catalog import Assignment, Service
from apps.service.queries.catalog import find_service, load_service
from apps.service.queries.reads import SYSTEM
from apps.service.schemas.assignments import AssignIn, AssignmentPatchIn
from apps.service.schemas.catalog import ServiceIn
from apps.service.schemas.recovery import ServiceRecoveredOut, ServiceRecoverIn
from apps.service.services.assignments import assign, update_assignment
from apps.service.services.catalog import create_service
from apps.service.services.service_images import _change_image
from apps.staff.models import Member
from apps.staff.queries.reads import live_members
from base import images
from base.recovery import LeftOut

#: Who a service made again from a separate copy came back without, said by their id (``service.service.recover``).
MEMBER_TERMINATED_LEFT = _("came back without the professional %(member)s: terminated in Staff")
MEMBER_GONE_LEFT = _("came back without the professional %(member)s: no longer in Staff")


# Not an assistant tool and no route: its one door is the recovery from a separate copy (BASE-F114), for a service the
# business no longer has at all.
@operation(
    "service.service.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=ServiceRecoverIn,
    output=ServiceRecoveredOut,
    ai=INTERNAL,
)
def recover_service(ctx: OperationContext, data: ServiceRecoverIn) -> dict:
    """A service of a separate copy the business no longer has, made again with who performed it there, all
    or nothing, each by the operation its screen uses: the service by ``service.service.create``; each professional the
    business still has by ``service.assignment.assign`` (SERVICE-F31), with their own minutes and price. One who left
    (terminated) or whom the business no longer has is not assigned: Staff no longer books them, and the output says it
    came back without them, and why (``left_out``). It is their main service only if the business gave them none since
    (the business's choice stays), and it comes back switched off, by ``service.assignment.update``, if it was. Its
    image of the library comes back as ``service.service.set_image`` sets it (SERVICE-F34); a photo of its own does not
    (``base.images.from_copy``). It keeps which of the copy's it is made again for (``stands_for``), for the apps whose
    records hang from that one (``queries.recovery.services_standing_for``)."""
    made = create_service(ctx, ServiceIn.model_validate(data.model_dump(include=set(ServiceIn.model_fields))))
    Service.objects.filter(pk=made.id).update(stands_for=data.stands_for)
    if image := images.from_copy(ctx, data.image):
        _change_image(ctx, find_service(made.id, None), image)
    asked = [one.member_id for one in data.assignments]
    staying = set(live_members().filter(pk__in=asked).values_list("pk", flat=True))
    known = set(Member.objects.filter(pk__in=asked).values_list("pk", flat=True))
    with_main = set(
        Assignment.objects.filter(member_id__in=asked, is_primary=True).values_list("member_id", flat=True)
    )
    for one in [one for one in data.assignments if one.member_id in staying]:
        assigned = assign(
            ctx,
            AssignIn(
                service_id=made.id,
                member_id=one.member_id,
                custom_duration=one.custom_duration,
                custom_price=one.custom_price,
                is_primary=one.is_primary and one.member_id not in with_main,
            ),
        )
        if not one.is_active:
            update_assignment(ctx, AssignmentPatchIn(id=assigned.id, is_active=False))
    left_out = [
        LeftOut(code="service.member_terminated", message=MEMBER_TERMINATED_LEFT % {"member": member})
        if member in known
        else LeftOut(code="service.member_not_in_business", message=MEMBER_GONE_LEFT % {"member": member})
        for member in asked
        if member not in staying
    ]
    return load_service(made.id, ctx.scope) | {"left_out": left_out}

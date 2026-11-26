"""A category the business no longer has, made again from a separate copy (BASE-F114), and what goes back into it: its
services and its subcategories, unless the business moved or changed them meanwhile.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.service import events
from apps.service.models.catalog import Category, Service, parent_problem
from apps.service.queries.catalog import find_service, load_service
from apps.service.queries.categories import find_category, load_category
from apps.service.queries.reads import SYSTEM
from apps.service.queries.recovery import left_by_deleting
from apps.service.schemas.catalog import ServiceOut
from apps.service.schemas.categories import CategoryIn, CategoryOut
from apps.service.schemas.recovery import CategoryRecoveredOut, CategoryRecoverIn, ServiceLinkIn, SubcategoryLinkIn
from apps.service.services.categories import create_category, lock_tree
from apps.service.services.writes import _actor, _apply
from base.recovery import LeftOut, carries_on

#: What a category made again from a separate copy came back without, said by its id (``service.category.recover``).
SERVICE_MOVED_LEFT = _("came back without the service %(service)s: moved to another category since")
SUBCATEGORY_MOVED_LEFT = _("came back without the subcategory %(category)s: moved elsewhere since")
SUBCATEGORY_LOOP_LEFT = _(
    "came back without the subcategory %(category)s: it would hang from one of its own subcategories"
)
#: Why one the business changed since the category came back, even without moving it, stays as it left it.
SERVICE_CHANGED_LEFT = _("came back without the service %(service)s: changed by the business meanwhile")
SUBCATEGORY_CHANGED_LEFT = _("came back without the subcategory %(category)s: changed by the business meanwhile")
#: Why nothing the business kept goes back into a category a recovery brought back before this one.
CATEGORY_BROUGHT_EARLIER = _(
    "the category %(category)s came back in an earlier recovery: what goes in it is the business's to decide"
)


# Not an assistant tool and no route: its one door is the recovery from a separate copy (BASE-F114), for a category
# the business no longer has at all.
@operation(
    "service.category.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=CategoryRecoverIn,
    output=CategoryRecoveredOut,
    ai=INTERNAL,
)
def recover_category(ctx: OperationContext, data: CategoryRecoverIn) -> dict:
    """A category of a separate copy the business no longer has, made again by ``service.category.create``. What it
    had inside it there and the business keeps where deleting it left it (SERVICE-F08) goes back into it afterwards,
    each by its own link, counted apart (``service.service.return_to_category``, ``service.category.return_to_parent``).
    What the business moved since stays where it is, and the output says the category came back without it, and why
    (``left_out``)."""
    parent_of = lock_tree()
    made = create_category(ctx, CategoryIn.model_validate(data.model_dump(include=set(CategoryIn.model_fields))))
    parent_of[made.id] = made.parent_id
    left_in = left_by_deleting(data.stands_for)
    moved = Service.objects.filter(pk__in=data.service_ids, category__isnull=False).order_by("id")
    left_out = [
        LeftOut(code="service.service_moved", message=SERVICE_MOVED_LEFT % {"service": pk})
        for pk in moved.values_list("pk", flat=True)
    ]
    for child in Category.objects.filter(pk__in=data.subcategory_ids, is_deleted=False).order_by("id"):
        if child.parent_id != left_in:
            message, code = SUBCATEGORY_MOVED_LEFT, "service.subcategory_moved"
        elif parent_problem(child.pk, made.id, parent_of):
            message, code = SUBCATEGORY_LOOP_LEFT, "service.subcategory_loop"
        else:
            continue
        left_out.append(LeftOut(code=code, message=message % {"category": child.pk}))
    return load_category(made.id) | {"left_out": left_out}


def _brought_back_now(ctx: OperationContext, category: Category) -> Category:
    """``category``, made again by the recovery that runs or by one it carries on (``base.recovery.carries_on``): one
    any other recovery brought back is the business's own, and nothing it kept goes back into it."""
    if category.created_by != _actor(ctx) and not carries_on(category.created_by):
        raise Conflict(str(CATEGORY_BROUGHT_EARLIER % {"category": category.pk}), code="service.category_brought_earlier")
    return category


# Not an assistant tool and no route: like the category's recover, its one door is the recovery from a separate copy.
@operation(
    "service.service.return_to_category",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=ServiceLinkIn,
    output=ServiceOut,
    ai=INTERNAL,
)
def return_service_to_category(ctx: OperationContext, data: ServiceLinkIn) -> dict:
    """A service the business kept without a category since it deleted the one it was in, put back into the category
    the running recovery made again for that one, as the screen changes it. One moved since stays where the business put
    it (``service.service_moved``). The category is held before the service, as an edit does."""
    category = _brought_back_now(ctx, find_category(data.category_id, None, hold=True))
    service = find_service(data.service_id, None, lock=True)
    if service.category_id is not None:
        raise Conflict(str(SERVICE_MOVED_LEFT % {"service": service.pk}), code="service.service_moved")
    if service.updated_at > category.created_at:
        raise Conflict(str(SERVICE_CHANGED_LEFT % {"service": service.pk}), code="service.service_changed")
    _apply(service, {"category_id": category.id}, ctx)
    service.save()
    record_event(ctx, events.SERVICE_UPDATED, {"id": str(service.id)})
    return load_service(service.id, ctx.scope)


# Not an assistant tool and no route: like the category's recover, its one door is the recovery from a separate copy.
@operation(
    "service.category.return_to_parent",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=SubcategoryLinkIn,
    output=CategoryOut,
    ai=INTERNAL,
)
def return_subcategory_to_parent(ctx: OperationContext, data: SubcategoryLinkIn) -> dict:
    """A subcategory the business kept where deleting its parent left it, hung again from the category the running
    recovery made again for that parent, as a move of the screen. One moved since stays where the business put it
    (``service.subcategory_moved``), and so does one that would hang from one of its own subcategories
    (``service.subcategory_loop``). The whole tree is held first, as a move does."""
    parent_of = lock_tree()
    parent = _brought_back_now(ctx, find_category(data.parent_id, None))
    child = find_category(data.category_id, None)
    if child.parent_id != left_by_deleting(data.stands_for):
        raise Conflict(str(SUBCATEGORY_MOVED_LEFT % {"category": child.pk}), code="service.subcategory_moved")
    if parent_problem(child.pk, parent.pk, parent_of):
        raise Conflict(str(SUBCATEGORY_LOOP_LEFT % {"category": child.pk}), code="service.subcategory_loop")
    if child.updated_at > parent.created_at:
        raise Conflict(str(SUBCATEGORY_CHANGED_LEFT % {"category": child.pk}), code="service.subcategory_changed")
    _apply(child, {"parent_id": parent.id}, ctx)
    child.save()
    record_event(ctx, events.CATEGORY_UPDATED, {"id": str(child.id)})
    return load_category(child.id)

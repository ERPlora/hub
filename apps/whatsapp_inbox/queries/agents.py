"""The people of the business a conversation can be assigned to."""

from django.db.models import Q, QuerySet
from live.context import OperationContext
from live.operations import operation

from apps.whatsapp_inbox.queries.reads import page, person_name
from apps.whatsapp_inbox.schemas.agents import AgentListIn, AgentPage
from base.models import HubUser, Membership


def team_roles(ctx: OperationContext) -> dict[str, str]:
    """``{username: role}`` of whoever has access to this business: control's memberships of the scope's host, read
    first (a query never joins two databases)."""
    return dict(
        Membership.objects.filter(host=ctx.scope.key, user__is_active=True).values_list("user__username", "role")
    )


def team(ctx: OperationContext, roles: dict[str, str] | None = None) -> QuerySet[HubUser]:
    """The people of this business in its own database (``base.HubUser``) who are still in it and have access to it."""
    return HubUser.objects.filter(username__in=list(team_roles(ctx) if roles is None else roles), is_active=True)


@operation(
    "whatsapp_inbox.agent.list",
    kind="query",
    permission="whatsapp_inbox.reply",
    input=AgentListIn,
    output=AgentPage,
    ai={
        "asks": {
            "en": (
                "which agents can answer the WhatsApp inbox?",
                "which of our people answer WhatsApp conversations?",
                "find Jorge among the WhatsApp agents",
            ),
            "es": (
                "¿quién del equipo atiende la bandeja de WhatsApp?",
                "¿qué personas pueden llevar las conversaciones de WhatsApp?",
                "busca a Jorge entre los agentes de WhatsApp",
            ),
        },
        "description": "The people of the business a WhatsApp conversation can be assigned to; search by name."
    },
)
def list_agents(ctx: OperationContext, params: AgentListIn) -> dict:
    roles = team_roles(ctx)
    rows = team(ctx, roles)
    if params.search:
        text = params.search.strip()
        rows = rows.filter(Q(name__icontains=text) | Q(username__icontains=text) | Q(email__icontains=text))
    rows = rows.order_by("name", "username", "id")
    return page(
        rows,
        params,
        lambda person: {"id": person.pk, "name": person_name(person), "role": roles[person.username]},
    )

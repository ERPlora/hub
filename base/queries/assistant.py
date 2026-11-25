"""What the assistant used this month (``base.assistant.usage``), the search of the tools a turn did not offer
(``base.assistant.find_tools``) and the search in the help docs (``base.docs.search``)."""

from django.utils import translation
from django.utils.translation import gettext, pgettext
from live import assistant as shared
from live.context import OperationContext
from live.errors import OperationError
from live.operations import AI, operation
from pydantic import ValidationError

from base import assistant
from base.permissions import VIEW_HOME
from base.schemas.assistant import (
    AssistantUsageIn,
    AssistantUsageOut,
    DocsSearchIn,
    DocsSearchOut,
    FindToolsIn,
    FindToolsOut,
)


# ── Assistant ───────────────────────────────────────────────────────────────────────────────────────────────────


@operation(
    "base.assistant.usage",
    kind="query",
    permission=VIEW_HOME,
    input=AssistantUsageIn,
    output=AssistantUsageOut,
    ai=AI(
        description=(
            "Reads this month's messages of the assistant (yours) of this business, as erplora.com counts them and "
            "«Usage and plan» in System shows them: how many are used, how many the plan includes a month and when "
            "they come back. Nothing else of the plan: that is base.plan.usage."
        ),
        asks={
            "en": ("how many assistant messages do we have left?", "how much of the assistant have we used this month?"),
            "es": ("¿cuántos mensajes le quedan al asistente?", "¿cuánto hemos gastado del asistente este mes?"),
        },
    ),
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile (in a turn, its route asked first).
    database=False,
)
def assistant_usage(ctx: OperationContext, data: AssistantUsageIn) -> dict:
    """This month's messages of the assistant as erplora.com counts them: used, of how many, and when
    they come back. What cannot be read is an error, never a number made up."""
    try:
        usage = assistant.gateway.month_usage(ctx.scope)
    except assistant.gateway.GatewayError:
        raise OperationError(
            gettext("The assistant's plan could not be read now."), code="base.assistant_unavailable", status=503
        ) from None
    return {
        "used": int(usage.get("used") or 0),
        "limit": int(usage.get("limit") or 0),
        "resets_at": usage.get("resets_at"),
        "demo": bool(usage.get("demo")),
    }


@operation(
    "base.assistant.find_tools",
    kind="query",
    permission=VIEW_HOME,
    input=FindToolsIn,
    output=FindToolsOut,
    ai=AI(
        description=(
            "Finds the tools for a task when none of the tools you were given does it: describe the task in a few "
            "words («list the products of a category», «create a product», «change an employee's schedule»). Returns "
            f"up to {shared.FOUND} tools, best first, with what each does; from your next step you can "
            "call them. Search before you say that something cannot be done here; if none fits, search again in other "
            "words."
        ),
        asks={
            "en": ("what else can you do with the stock?", "can you also change the staff's schedules?"),
            "es": ("¿qué más puedes hacer con el inventario?", "¿también puedes cambiar los horarios del personal?"),
        },
    ),
)
def find_tools(ctx: OperationContext, data: FindToolsIn) -> dict:
    """The tools of the person's catalogue that do the task ``data.query`` describes: none they may not use."""
    found = assistant.relevance.found(assistant.tools.catalog(ctx), data.query, ctx.language)
    return {"tools": [{"name": shared.tool_name(op.name), "description": shared.description(op)} for op in found]}


@operation(
    "base.docs.search",
    kind="query",
    permission=VIEW_HOME,
    input=DocsSearchIn,
    output=DocsSearchOut,
    ai=AI(
        description=(
            "Searches ERPlora's help and the documentation of its apps for how-to questions (how to do something, what "
            "a screen or option means, plans and prices): returns up to 8 cited excerpts. Not for the business's own "
            "records."
        ),
        asks={
            "en": (
                "how do I close the till at night?",
                "what does a shared device mean?",
                "how much is the Standard plan?",
            ),
            "es": (
                "¿cómo se hace una devolución?",
                "¿qué significa dispositivo compartido?",
                "¿cuánto cuesta el plan Standard?",
            ),
        },
    ),
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile (in a turn, its route asked first).
    database=False,
)
def docs_search(ctx: OperationContext, data: DocsSearchIn) -> DocsSearchOut:
    """The excerpts of ERPlora's documentation nearest to the person's question, in their language (saas
    ASSISTANT-F28): erplora.com's one index, never one of the Hub's. What it cannot answer is an error the assistant
    relays, never excerpts made up."""
    try:
        found = DocsSearchOut.model_validate(assistant.gateway.searched_docs(ctx, query=data.query, limit=data.limit))
    except (assistant.gateway.GatewayError, ValidationError):
        with translation.override(ctx.language):
            message = gettext("ERPlora's documentation could not be searched now.")
        raise OperationError(message, code="base.assistant_unavailable", status=503) from None
    # Each excerpt with the line the answer cites it by (hub#1079): its headings, else its path, after «Source» in the
    # person's language, for the model to write as it comes.
    with translation.override(ctx.language):
        source = pgettext("assistant answer", "Source")
    return DocsSearchOut(
        results=[
            excerpt.model_copy(update={"cite": f"{source}: {excerpt.heading or excerpt.path}"})
            for excerpt in found.results
        ]
    )


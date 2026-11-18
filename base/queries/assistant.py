"""What the assistant used this month (``base.assistant.usage``) and the search in the help docs (``base.docs.search``)."""

from django.utils import translation
from django.utils.translation import gettext, pgettext
from live.context import OperationContext
from live.errors import OperationError
from live.operations import AI, operation
from pydantic import ValidationError

from base import assistant
from base.permissions import VIEW_HOME
from base.schemas import AssistantUsageIn, AssistantUsageOut, DocsSearchIn, DocsSearchOut


# ── Assistant ───────────────────────────────────────────────────────────────────────────────────────────────────


@operation(
    "base.assistant.usage",
    kind="query",
    permission=VIEW_HOME,
    input=AssistantUsageIn,
    output=AssistantUsageOut,
    ai={"description": "Not an assistant tool (the panel's own footer: the messages of the month left)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_usage(ctx: OperationContext, data: AssistantUsageIn) -> dict:
    """This month's messages of the assistant as erplora.com counts them: used, of how many, and when
    they come back. What cannot be read is an error, never a number made up."""
    try:
        usage = assistant.gateway.usage(ctx.scope)
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

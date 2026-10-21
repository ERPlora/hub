"""Ninja routes of the WhatsApp inbox: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a conversation's ``id`` travels in the input. What erplora.com
pushes (a message, a delivery status, the channel's state) has no route here: ``base`` mounts
``/internal/whatsapp/*`` and runs those operations as the system (WORKBOOK «Contrato con base»).
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.whatsapp_inbox import queries, services
from apps.whatsapp_inbox.schemas import (
    AgentListIn,
    AssignIn,
    ByPhoneIn,
    ConversationListIn,
    ConversationRefIn,
    LinkCustomerIn,
    MessageRefIn,
    MessageListIn,
    NoteAddIn,
    NoteListIn,
    NoteRefIn,
    SendIn,
    SetStatusIn,
    TemplateCreateIn,
    TemplateListIn,
    TemplateRefIn,
    TemplateUpdateIn,
)

router = Router(tags=["whatsapp_inbox"])


# Conversations


@bind(router, "whatsapp_inbox.conversation.list", "/whatsapp_inbox/conversations")
async def conversation_list(request, params: Query[ConversationListIn]):
    return await run_operation(request, queries.list_conversations, params)


@bind(
    router, "whatsapp_inbox.conversation.detail", "/whatsapp_inbox/conversations/detail"
)
async def conversation_detail(request, params: Query[ConversationRefIn]):
    return await run_operation(request, queries.conversation_get, params)


@bind(
    router,
    "whatsapp_inbox.conversation.by_phone",
    "/whatsapp_inbox/conversations/by_phone",
)
async def conversation_by_phone(request, params: Query[ByPhoneIn]):
    return await run_operation(request, queries.conversation_by_phone, params)


@bind(
    router,
    "whatsapp_inbox.conversation.summary",
    "/whatsapp_inbox/conversations/summary",
)
async def conversation_summary(request):
    return await run_operation(request, queries.conversation_summary)


@bind(
    router,
    "whatsapp_inbox.conversation.mark_read",
    "/whatsapp_inbox/conversations/mark_read",
)
async def conversation_mark_read(request, data: ConversationRefIn):
    return await run_operation(request, services.mark_read, data)


@bind(
    router, "whatsapp_inbox.conversation.assign", "/whatsapp_inbox/conversations/assign"
)
async def conversation_assign(request, data: AssignIn):
    return await run_operation(request, services.assign, data)


@bind(
    router,
    "whatsapp_inbox.conversation.set_status",
    "/whatsapp_inbox/conversations/set_status",
)
async def conversation_set_status(request, data: SetStatusIn):
    return await run_operation(request, services.set_status, data)


@bind(
    router,
    "whatsapp_inbox.conversation.link_customer",
    "/whatsapp_inbox/conversations/link_customer",
)
async def conversation_link_customer(request, data: LinkCustomerIn):
    return await run_operation(request, services.link_customer, data)


@bind(
    router, "whatsapp_inbox.conversation.erase", "/whatsapp_inbox/conversations/erase"
)
async def conversation_erase(request, data: ConversationRefIn):
    return await run_operation(request, services.erase, data)


# Messages


@bind(router, "whatsapp_inbox.message.list", "/whatsapp_inbox/messages")
async def message_list(request, params: Query[MessageListIn]):
    return await run_operation(request, queries.list_messages, params)


@bind(
    router, "whatsapp_inbox.message.send", "/whatsapp_inbox/messages/send", status=201
)
async def message_send(request, data: SendIn):
    return await run_operation(request, services.send_message, data)


@bind(router, "whatsapp_inbox.message.retry", "/whatsapp_inbox/messages/retry")
async def message_retry(request, data: MessageRefIn):
    return await run_operation(request, services.retry_message, data)


# Notes


@bind(router, "whatsapp_inbox.note.list", "/whatsapp_inbox/notes")
async def note_list(request, params: Query[NoteListIn]):
    return await run_operation(request, queries.list_notes, params)


@bind(router, "whatsapp_inbox.note.add", "/whatsapp_inbox/notes", status=201)
async def note_add(request, data: NoteAddIn):
    return await run_operation(request, services.add_note, data)


@bind(router, "whatsapp_inbox.note.delete", "/whatsapp_inbox/notes/delete")
async def note_delete(request, data: NoteRefIn):
    return await run_operation(request, services.delete_note, data)


# Templates, channel and team


@bind(router, "whatsapp_inbox.template.list", "/whatsapp_inbox/templates")
async def template_list(request, params: Query[TemplateListIn]):
    return await run_operation(request, queries.list_templates, params)


@bind(router, "whatsapp_inbox.channel.get", "/whatsapp_inbox/channel")
async def channel_get(request):
    return await run_operation(request, queries.channel_get)


@bind(router, "whatsapp_inbox.agent.list", "/whatsapp_inbox/agents")
async def agent_list(request, params: Query[AgentListIn]):
    return await run_operation(request, queries.list_agents, params)


@bind(router, "whatsapp_inbox.template.create", "/whatsapp_inbox/templates", status=201)
async def template_create(request, data: TemplateCreateIn):
    return await run_operation(request, services.create_template, data)


@bind(router, "whatsapp_inbox.template.update", "/whatsapp_inbox/templates/update")
async def template_update(request, data: TemplateUpdateIn):
    return await run_operation(request, services.update_template, data)


@bind(router, "whatsapp_inbox.template.retry", "/whatsapp_inbox/templates/retry")
async def template_retry(request, data: TemplateRefIn):
    return await run_operation(request, services.retry_template, data)


@bind(router, "whatsapp_inbox.template.delete", "/whatsapp_inbox/templates/delete")
async def template_delete(request, data: TemplateRefIn):
    return await run_operation(request, services.delete_template, data)

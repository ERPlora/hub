"""The Hub's codes for what went wrong with a message or a template, and its words for them."""

from django.utils.translation import gettext_lazy as _

from apps.whatsapp_inbox.models import Message, Template

# Why a hand-over to erplora.com did not end well. A row keeps only the Hub's code (and, for a refusal of Meta's the
# Hub has no name for, Meta's words as they came): the text is said when the row is read, in the reader's language,
# never in the one of whoever wrote it (the worker writes in English).
NOT_CONNECTED = _(
    "WhatsApp is not connected. Connect the business's number in Settings to receive and send messages."
)
CAP_REACHED = _(
    "You have used every WhatsApp message of your plan this month: nothing can be sent until next month "
    "or until you upgrade the plan."
)
SEND_REFUSED = _("erplora.com did not send the message.")
#: Meta's 190, as erplora.com says it (``whatsapp.reconnect_needed``): only connecting the number again fixes it.
RECONNECT_NEEDED = _("WhatsApp's permission for your number expired: connect it again.")
SAAS_UNREACHABLE = _("erplora.com did not answer: the message has not left. Try again.")
SEND_UNKNOWN = _(
    "erplora.com did not confirm the message. Try again: it is never sent twice."
)
CONVERSATION_ERASED = _("The conversation was erased before the message left.")
TEMPLATE_REFUSED = _("Meta did not accept the template.")
META_UNREACHABLE = _("Meta did not answer. Try again in a few minutes.")
META_RATE_LIMITED = _("Meta asks to wait before trying again. Try again in a few minutes.")
TEMPLATE_SAAS_UNREACHABLE = _("erplora.com did not answer: the template has not left. Try again.")
TEMPLATE_UNKNOWN = _("erplora.com did not confirm the template. Try again: it is never registered twice.")
DELETE_SAAS_UNREACHABLE = _("erplora.com did not answer: Meta still has the template. Try again.")
DELETE_UNKNOWN = _("erplora.com did not confirm that Meta deleted the template. Try again.")
#: The Hub's own code of a hand-over that could not take the header's file: it is no longer in the business's store.
HEADER_SAMPLE_MISSING_CODE = "whatsapp_inbox.header_sample_missing"
HEADER_SAMPLE_MISSING = _("The header's file is no longer in the business's files: choose it again with Edit.")
MESSAGE_HEADER_SAMPLE_MISSING = _(
    "The header's file is no longer in the business's files: send the template again choosing its file."
)

SEND_REFUSED_CODE = "whatsapp_inbox.send_refused"
TEMPLATE_REFUSED_CODE = "whatsapp_inbox.template_refused"
SAAS_UNREACHABLE_CODE = "whatsapp_inbox.saas_unreachable"
SEND_UNKNOWN_CODE = "whatsapp_inbox.send_unknown"
#: A message's code → the Hub's words for it.
_MESSAGE_REASONS = {
    "whatsapp_inbox.meta_unreachable": META_UNREACHABLE,
    HEADER_SAMPLE_MISSING_CODE: MESSAGE_HEADER_SAMPLE_MISSING,
    "whatsapp_inbox.cap_reached": CAP_REACHED,
    "whatsapp_inbox.channel_not_connected": NOT_CONNECTED,
    "whatsapp_inbox.reconnect_needed": RECONNECT_NEEDED,
    SAAS_UNREACHABLE_CODE: SAAS_UNREACHABLE,
    SEND_UNKNOWN_CODE: SEND_UNKNOWN,
    "whatsapp_inbox.conversation_erased": CONVERSATION_ERASED,
}
#: A template's code → the Hub's words for it (the same for a hand-over and for a deletion).
_TEMPLATE_REASONS = {
    "whatsapp_inbox.meta_unreachable": META_UNREACHABLE,
    "whatsapp_inbox.meta_rate_limited": META_RATE_LIMITED,
    "whatsapp_inbox.channel_not_connected": NOT_CONNECTED,
    "whatsapp_inbox.reconnect_needed": RECONNECT_NEEDED,
    HEADER_SAMPLE_MISSING_CODE: HEADER_SAMPLE_MISSING,
}


def message_reason(row: Message) -> str:
    """Why it did not go well, in the reader's language: the Hub's words for its own codes (a row written before
    the code alone was kept says it so too); a refusal it has no name for, as Meta or erplora.com said it."""
    own = _MESSAGE_REASONS.get(row.error_code)
    if own is not None:
        return str(own)
    if row.error_code == SEND_REFUSED_CODE and not row.error_message:
        return str(SEND_REFUSED)
    return row.error_message


def template_reason(row: Template) -> str:
    """Why its last hand-over or deletion did not end well, in the reader's language (as ``message_reason``); with
    no answer, the deletion's words while it is being deleted and the hand-over's otherwise."""
    code = row.submit_error_code
    own = _TEMPLATE_REASONS.get(code)
    if own is not None:
        return str(own)
    deleting = row.delete_state == Template.DeleteState.PENDING
    if code == SAAS_UNREACHABLE_CODE:
        return str(DELETE_SAAS_UNREACHABLE if deleting else TEMPLATE_SAAS_UNREACHABLE)
    if code == SEND_UNKNOWN_CODE:
        return str(DELETE_UNKNOWN if deleting else TEMPLATE_UNKNOWN)
    if code == TEMPLATE_REFUSED_CODE and not row.submit_error:
        return str(TEMPLATE_REFUSED)
    return row.submit_error

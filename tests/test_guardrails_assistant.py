"""Guardrail of the assistant's tool descriptions (hub#1140): the card of a write is the person's confirmation.

``base.assistant.instructions`` tell the model «To change something, call its tool: the person sees a card and confirms
it before it runs». A tool whose ``ai=`` description tells it to ask, confirm or wait for a yes in the chat before the
call is asked about in the chat and its card never shows: the model answers «are you sure…?» and the change is never
made from the chat. Seen with the real model in Reservations (hub#1105: «Ask first.» on cancelling, deleting,
unblocking and taking off the waitlist, offered 4th to 10th), in Tables (hub#1081, ``table.session.delete``) and in the
Cash register (hub#1138: «tell the person its summary, then close»).

Here every assistant tool of the Hub (``base.assistant.is_tool``, every app and the platform, reads too: a read needs
no yes either) is read sentence by sentence with :func:`stops_in_the_chat`, proven by the old texts and their wordings
(the positive controls) and by sentences that must pass. Its known limit: it reads prose, so a new wording of the same
instruction («get their OK beforehand») passes until it is added here; :data:`IN_THE_CHAT` says which ones it reads.

No tool is left out: the last nine that still said it (Time tracking, Automations, Staff and Invoicing, kept aside while
pull requests edited their files) were fixed by hub#1175, and a new one fails here.
"""

import re

from live import assistant as shared
from live.operations import registry

from base import assistant

#: Names, never instructions: a label of the screen («Ask me first»), code (`ask_first`) and a dotted name (a tool, a
#: domain, a number with decimals) are blanked before the sentences are read, so a description may name them.
NAMES = re.compile(r"«[^»]*»|`[^`]*`|\b\w+(?:\.\w+)+\b")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

#: What makes the model stop in the chat before the card, each read within one sentence.
IN_THE_CHAT = (
    # «Ask first.», «Ask the person before doing it.», «confirm the times and the reason first»
    re.compile(r"\b(?:ask|confirm)\b[^.]*\b(?:first|before|beforehand)\b", re.IGNORECASE),
    # «Confirm it: what the owner changed is lost.», «confirm it with the person»
    re.compile(r"\bconfirm\s+(?:it|this|that|them)\b", re.IGNORECASE),
    # «tell the person its summary, then close»: the model tells it and waits for an answer
    re.compile(r"\b(?:tell|show)\b[^.]*\b(?:the\s+person|them)\b[^.]*\bthen\b", re.IGNORECASE),
    # «wait for their yes»
    re.compile(r"\bwait\b[^.]*\b(?:yes|ok|okay|confirmation|go-ahead|answer|reply)\b", re.IGNORECASE),
    # «Read it before rectifying and tell the person this preview»: the read before a write tells it and stops there
    re.compile(r"\bbefore\b[^.]*\b(?:tell|show)\b[^.]*\b(?:the\s+person|them)\b", re.IGNORECASE),
)

#: A negation right before the instruction («do not stop at the summary nor wait for a yes», «never ask them first»):
#: up to two words between it and the verb, never across a comma or a colon.
NEGATED = re.compile(r"\b(?:not|nor|never|no|don't)\b(?:\s+\w+){0,2}\s*$", re.IGNORECASE)


def stops_in_the_chat(description: str) -> list[str]:
    """The sentences of ``description`` that tell the model to ask, confirm or wait in the chat before the tool's
    card, as written after :data:`NAMES` is blanked; ``[]`` when none does."""
    found = []
    for sentence in SENTENCE_END.split(NAMES.sub("·", description)):
        for pattern in IN_THE_CHAT:
            match = pattern.search(sentence)
            if match and not NEGATED.search(sentence[: match.start()]):
                found.append(sentence.strip())
                break
    return found


def tools() -> dict[str, str]:
    """Every assistant tool of the Hub, by name, with its description."""
    return {name: shared.description(op) for name, op in sorted(registry.items()) if assistant.is_tool(op)}


def test_the_guard_reads_the_old_texts_and_their_wordings():
    said = [
        "A check with something ordered is refused; an empty one is voided in Sales. Ask first.",  # Tables, hub#1140
        "Its time becomes free. Ask the person before doing it.",  # Appointments, Online bookings
        "Cancelling keeps the record and is usually what is wanted; ask first.",
        "Cancelling keeps its history and is usually what is wanted; ask the person first.",
        "The ones it had stay. Always ask the person before.",  # the wording hub#1141's review added
        "This rewrites the legal working-day record: confirm the times and the reason first.",  # Time tracking
        "Cannot be undone: confirm it first.",  # Automations
        "It is the person's decision: confirm it with them first.",
        "Confirm it: what the owner changed is lost.",
        "It changes how it is billed: confirm it with the person.",  # Menus
        "Read cash_register.session.closing_summary first, tell the person its summary, then close it.",  # hub#1138
        "Read the preview first, show them the total, then charge it.",
        "Call it once the person says yes; wait for their yes in the chat.",
        "Check the role with staff.role.list; if it is not there, ask the person before creating it.",  # Staff
        # The read before a write, hub#1175: it tells the preview and stops there, before the write's card.
        "Changes nothing and takes no number. Read it before rectifying and tell the person this preview; when the "
        "invoice cannot be rectified it says why.",  # Invoicing
        "Changes nothing. Read it before closing and tell the person this summary; with none, no.",  # the old till
        "Before you run it, show them what it would send.",
    ]
    assert [text for text in said if not stops_in_the_chat(text)] == []


def test_the_guard_lets_through_what_no_instruction_to_ask_in_the_chat_is():
    fine = [
        "Use it to answer what they ask. Free it or move the reservation first.",  # Reservations' own guard
        "One with `ask_first` only goes in an «Ask the assistant» step with «Ask me first».",  # flow.catalog.read
        "Read cash_register.session.closing_summary first with the same count; then, in the same answer where you "
        "tell the person its summary, call this tool: do not stop at the summary nor wait for a yes in the chat, "
        "its card is where the person confirms.",  # the close of hub#1138
        "Hands a message that has not left (erplora.com did not answer or did not confirm it) to the queue.",
        "Confirm a pending appointment (a booking the customer made, waiting for review).",
        "Find the closed check with table.session.list(status=closed), never ask them for it.",
        "A name that fits several apps is refused naming them: ask the person which one.",
        "Read them with staff.role.list first.",
        "Read it before writing to anybody.",
        "The summary of closing the drawer, before closing it: what closing would give.",  # a read says what it is for
        "To rectify, read it with the same reason and type and, in the same answer where you tell the person this "
        "preview, call this tool: its card is the confirmation.",
        "A role the business does not have is refused before the card: name the roles it has and let the person pick.",
    ]
    assert {text: stops_in_the_chat(text) for text in fine if stops_in_the_chat(text)} == {}


def test_no_tool_tells_the_model_to_ask_in_the_chat_before_its_card():
    described = tools()
    assert "table.session.close" in described  # the sweep reaches the apps' tools, not only the platform's
    told = {name: stops_in_the_chat(text) for name, text in described.items()}
    assert {name: sentences for name, sentences in told.items() if sentences} == {}

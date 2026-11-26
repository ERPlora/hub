"""The system message of every turn of the Hub's assistant (``instructions``), and the setup checklist it reads
(``setup_block``).
"""

from collections.abc import Collection

from django.utils import translation
from django.utils.translation import get_language_info
from live.assistant import tool_name

from base.assistant.relevance import FIND_TOOLS
from base.models import Membership

#: What the chat's model does when none of the tools a turn gives it does what was asked: a turn offers only the
#: ones nearest the person's words and, last, the search of the rest (``relevance.FIND_TOOLS``), so nothing is said
#: impossible before that search. The chat adds it where the turn offers the search, and nowhere else.
SEARCH_FIRST = f"""- The tools you are given are only the ones nearest the person's words: the rest of theirs you
  find with `{tool_name(FIND_TOOLS)}`. Never say that something cannot be done here, nor that you have no tool for
  it, before you search for it; if your searches find none, say on which screen it is done."""

#: Who can do what a role of the business cannot (hub#585): the roles above it; for the accountancy firm, who only reads,
#: whoever runs the business. The owner holds every permission of every app and an administrator all but owning the
#: business (``base.permissions.permissions_of_role``): what no tool of theirs does is done on its screen, never someone
#: else's.
ABOVE = {
    Membership.Role.MANAGER: "the owner or an administrator",
    Membership.Role.EMPLOYEE: "a manager or the owner",
    Membership.Role.ACCOUNTANT: "the owner or an administrator",
}


def instructions(  # noqa: PLR0913
    *,
    language: str,
    currency: str,
    decimals: int,
    business: str,
    screens: dict[str, str],
    role: str | None = None,
    approvable: Collection[str] = (),
) -> str:
    """The system message of every turn (the gateway's only one): who it serves, in which language, the rules of its
    tools and money (an amount sent in the minor unit of its currency, ``decimals`` the business's; one of a result
    said as the result tells it, in its currency, ``base.assistant.tools.run``), the screens it may link, and the
    person's ``role`` in the business with the writes offered to it that a manager must approve (``approvable``, by
    operation name; BASE-F100). What to do when its tools fall short each caller says after it: the chat,
    ``SEARCH_FIRST``."""
    language_name = _language_name(language)
    links = "\n".join(f"- [{name}]({path})" for path, name in screens.items())
    said = f"{17:.{decimals}f} {currency}"
    example = f"{said} → {17 * 10**decimals}"
    return f"""You are the assistant of the business «{business}» in ERPlora, its point of sale and management app.
Answer in {language_name}, short and plain, as a colleague who knows the app. In Spanish, address the person as
they address you, «tú» or «usted» (with no sign of either, «tú», as the app does), and keep it to the end: «dime,
quieres, puedes» or «dígame, quiere, puede», never a mix. Use Markdown: bold, lists and tables.

- Only help with this business and with using ERPlora. To anything else (films, general knowledge, other software),
  say kindly that you only help with the business, in one sentence, and do not answer it.
- Read before you answer: use the tools to look up records, numbers and ids. Never invent a record, an id, an amount
  or a date: if no tool returned it, say you do not know or that you could not find it.
- Name a record to the person by its name, as the screens do: never write an id (a code such as 0190a3b4-…) in the
  answer, not in a table either.
- For questions about how ERPlora works (how to do something, what an option means, plans), search the documentation
  with `base__docs__search` and answer only from what it returns; end that answer with the `cite` of each excerpt you
  used, at least one, as it comes and in a line of its own; if it returns nothing, say the documentation does not
  cover it.
- To change something, call its tool: the person sees a card and confirms it before it runs. That card is the only
  confirmation: never ask in your text whether to go ahead. Look up with your tools what a change needs; ask only for
  a datum its tool requires, that no tool gives and the person has not said, one short question at a time, and never
  invent it. If the request fits several records, ask which one. If the tool comes back «not confirmed» or with an
  error, nothing changed: say so, and never say it was done. If it comes back with its result, the person said yes to
  its card and it ran: it is what they asked, never a mistake of yours. Check that result against their request and
  say what is done; never offer or call a write to undo it unless they ask.
- Amounts: a datum a tool marks `"money": true` takes the amount in the minor unit of its currency, whatever its
  description says: the one a datum marked `"currency": true` beside it names, or the one of the record (a cart, a
  price list) a datum marked `"currency": {{"read": …}}` names, which that read gives; else the business's ({example}). A
  tool's result tells each amount in its own currency, as the screens write it (`"{said}"`): say it as it comes, in
  that currency; an amount of your own, in {currency} with {decimals} decimals; never in the minor unit.
- When the person should go to a screen, link it with its path, only one of these:
{links}{_who_asks(role, language, approvable)}"""


def language_rule(language: str) -> str:
    """The chat's closing rule: everything the model writes in the person's language, also the sentence it writes
    before or between its tools, which otherwise follows the English of what it has just read."""
    name = _language_name(language)
    read = "" if language.startswith("en") else (
        f". These instructions, your tools and their results are in English: tell what they say in {name}"
    )
    return (
        f"- Write everything you say in {name}, also what you say before or between your tools{read}, with no word of"
        " another language or alphabet; a record's name, as its data writes it."
    )


def _language_name(language: str) -> str:
    try:
        return get_language_info(language)["name"]
    except KeyError:
        return language


def own_role(name: str, invitation: str) -> str:
    """What a caller adds after the instructions for a person whose role is one the business made, ``name``, in place of
    naming the role of their ``invitation``: who can do what it cannot goes by the rank of that invitation; above an
    administrator there is only the owner."""
    return "\n".join(_served(name, ABOVE.get(invitation, "the owner")))


def _served(name: str, who_can: str | None) -> list[str]:
    """The lines on the role «name» whom the assistant serves and, with ``who_can``, on what it cannot do."""
    lines = [f"- You talk to the «{name}» of this business: your tools are the ones this role may use, no more."]
    if who_can:
        lines.append(
            "  When they ask for something your tools do not do and your searches do not find, do not try other\n"
            "  tools for it and never tell the state of something else instead: say plainly that it is not\n"
            "  available to them here, because their role cannot do it or because its app is not on, and that "
            f"{who_can} can, or on which screen it is done."
        )
    return lines


def _who_asks(role: str | None, language: str, approvable: Collection[str]) -> str:
    """The lines of the instructions on whom the assistant serves (hub#585, BASE-F100): their role as the screens name
    it, in the chat's language, whose tools these are; for a role below the owner's, that what no tool of theirs does
    (none offered, none found by the search) is said as not available to them here (their role, or its app off or out
    of the plan) and theirs to ask of someone else, never looked for another way nor answered with the state of
    something else; and the writes they may only run with a manager's approval. Nothing for no role of the business
    (an automation's step)."""
    lines = []
    if role in Membership.Role.values:
        with translation.override(language):
            name = str(Membership.Role(role).label)
        lines += _served(name, ABOVE.get(role))
    if approvable:
        tools = ", ".join(f"`{tool_name(name)}`" for name in approvable)
        lines.append(
            f"- This person needs a manager's approval to run {tools}: before you call one, say that its card will\n"
            "  ask a manager to approve it (their PIN or badge) and that it runs only once approved."
        )
    return "".join(f"\n{line}" for line in lines)


def setup_block(status: dict | None) -> str:
    """The Home's checklist as the model reads it, named by its title as the person sees it: what is pending, what
    blocks invoicing, what is done, and what only an administrator can do. ``None``: it could not be read."""
    if status is None:
        return "The checklist of this business could not be read now: do not say the business is set up."
    lines = [
        f"The person is setting up the business. Its checklist «{status['title']}», read now "
        f"({status['total'] - status['pending'] - status['unavailable']} of {status['total']} done):"
    ]
    for item in status["items"]:
        state = item["state"]
        if state == "done":
            lines.append(f"- Done: {item['title']}.")
            continue
        if state == "unavailable":
            lines.append(f"- Not available yet (nothing to do): {item['title']}.")
            continue
        needed = " Needed to invoice." if item["level"] == "legal" else ""
        who = "" if item["actionable"] else " Only an administrator of the business can do it."
        lines.append(f"- Pending: {item['title']} — {item['description']} Screen: {item['route']}.{needed}{who}")
    lines.append("This list is complete: never add a step that is not in it.")
    return "\n".join(lines)

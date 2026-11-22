"""The Hub's assistant: chat and voice in the Hub against erplora.com's AI gateway (``saas`` ``assistant/internal.py``),
without the ORM.

The mechanics that do not depend on the gateway are ``live.assistant``'s, shared with the SaaS's panel; these modules
give them the Hub's own: what a turn offers (``relevance``), the tools (``tools``), the card of a write (``cards``), the
checks at start of what the operations declare for it (``checks``), the system message (``prompt``) with what it knows of
the business (``business_facts``) and erplora.com's gateway with the turn's answer as it comes (``gateway``). Importing
the package loads them all, and with them their checks.
"""

from . import relevance as relevance, tools as tools, cards as cards, checks as checks, prompt as prompt
from . import gateway as gateway, business_facts as business_facts

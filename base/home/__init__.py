"""The Home's rules: what base does with the modules' steps, panels and counters.

Every module declares in its ``LiveAppConfig`` its steps of «Finish setting up your business» (``setup``), its
panels of the dashboard (``widgets``) and its counters of the bell (``bell``), each naming a query of its own
``queries.py``. Base aggregates them in three live queries of ``base/queries/`` (``base.setup.status``,
``base.widget.list``, ``base.bell.counters``) with the old hub's rules (``crates/runtime/src/setup_status.rs``):

- only the modules on in the scope bring anything, and a module kept out of the store (``listed = False``, the
  reference app ``demo``) only where it shows at all (:func:`shown_modules.shown_modules`);
- a step reads the FIRST row of its query, run by name as the person of the request: done when every condition
  of ``configured_when`` passes on it, pending without a row; a step whose query fails is left out and logged
  (a false «you are missing X» sends the person to fix what may be fine);
- the level is base's, never the module's: ⛔ legal for the list base fixes (``LEGAL_STEPS``) and, where the step's
  row says the hub files in production, for the ones of ``LEGAL_IN_PRODUCTION``; else ``required`` gives functional
  and its absence recommended;
- whoever lacks a step's permission is not told about it, except a pending ⛔ (``actionable: false``): it is what
  will stop their invoice, whoever clears it.

A counter whose figure moves as time passes, with no event (a job waiting a minute with no device alive to print
it), names in ``bell_refresh_every`` of its module's ``LiveAppConfig`` (counter key → seconds) how often the bell reads
it again besides its ``refresh_on``: the bell is told the shortest period among the counters the person may see
(:func:`bell_counters.bell_refresh_every`), and ``base.E007`` checks the declarations at start
(:func:`bell_counters.bell_refresh_errors`).

The cards of System › «Usage and plan» are a hook of base, not of ``live.meta``: a module names in ``system_cards``
the Vue components of its own ``frontend/components/`` that paint them (:func:`system_cards.system_cards`), base lists
those of the modules on that the person may see (``base.system.cards``) and the SPA mounts each one, as a panel with a
``component`` of its own; ``base.E015`` checks the declarations at start (:func:`system_cards.system_card_errors`).
What a card says is its app's: base never learns what is in it.

An app also says where a business must have it on: ``mandatory`` on its ``LiveAppConfig``, the countries (or
``"all"``) and whether the platform turns it on by itself. While it is off in a business of one of them, the list
carries a step of the platform that asks to turn it on (:func:`mandatory_apps.mandatory_steps`); ``base.E016`` checks
the declarations at start (:func:`mandatory_apps.mandatory_errors`). Base names no app: each says it.

The device's notices (``notices``; ``base.notice.list``) run the same way: every row of a notice's query that passes
its ``when`` is told, with the texts filled in from the row in the person's language
(:func:`device_notices.device_notices`); the shell tells each one once on the device, with the installed app's system
notice.

No ORM here: ``queries.py`` reads what the platform's own steps and counters need.
"""

from . import (
    bell_counters as bell_counters,
    device_notices as device_notices,
    mandatory_apps as mandatory_apps,
    module_hooks as module_hooks,
    plan_meters as plan_meters,
    setup_steps as setup_steps,
    shown_modules as shown_modules,
    step_conditions as step_conditions,
    system_cards as system_cards,
    widgets as widgets,
)

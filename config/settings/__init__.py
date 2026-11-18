"""Django settings of the Hub: a control database plus one database per hub, the hub chosen by the Host's label.

Configuration comes from the environment (or a ``.env`` file) through python-decouple. ``DEBUG`` is
off unless set: local development opts in with ``DEBUG=True`` in ``.env`` and then gets defaults for
``compose.yaml`` and the local SaaS; without it the settings demand ``SECRET_KEY``, ``SAAS_URL`` and
``INTERNAL_SHARED_SECRET``. The production variables are the contract of ERPlora/aws's ``stacks/prod/apps.tf``
(its README, «Contrato app ↔ infra»).

Each module of this package holds one concern, read in this order; Django reads the upper-case names of all of
them from here.
"""

from config.settings import (
    core,
    application,
    backends,
    saas_contract,
    businesses,
    erplora,
    web,
    modules,
    mail,
    observability,
)

for _concern in (core, application, backends, saas_contract, businesses, erplora, web, modules, mail, observability):
    globals().update((name, value) for name, value in vars(_concern).items() if name.isupper())

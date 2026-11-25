"""The Hub's modules, registered as products in the SaaS's ``shared`` schema.

Each module (``kind = "app"``) is one row of ``shared.app`` and up to two of ``shared.app_doc``,
written by ``register_apps`` from what the code already says: the ``LiveAppConfig`` metadata in
English and its Spanish catalogue, the icon baked in ``frontend/generated/app-icons.json`` and the
customer's part of ``WORKBOOK.md`` (Spanish) and of ``WORKBOOK.en.md`` (its versioned translation).

- ``workbooks.user_part`` cuts the customer's part of a WORKBOOK, without its HTML comments.
- ``app_registry.build_registry`` reads it all without a database or the network: ``register_apps
  --check`` and the image's build run it; every problem is gathered, naming the app and the field.
- ``register_apps.register_apps`` writes the registry in one transaction on the ``shared`` alias.
- ``static_files.AppImagesFinder`` publishes ``apps/<id>/docs/img/`` as ``static/catalog/<id>/img/``.
- ``verticals.known_verticals`` and ``verticals.template_apps`` derive each vertical's template apps.
- ``errors`` holds what they raise: ``CatalogError`` and the errors that refine it.

The module ``register_apps`` is the only one that imports ``shared.models`` and names the ``shared`` alias: the
explicit exception to «only ``services.py`` and ``queries.py`` touch the ORM», as
``base/tenancy/migrator/`` is for the DDL (``base/tests/test_shared_lint.py``). It is no
``@operation``: it runs for no hub and no user, with the ``hub_shared`` role, which may only
``SELECT``, ``INSERT`` and ``UPDATE`` those two tables.
"""

from . import (
    app_registry as app_registry,
    errors as errors,
    register_apps as register_apps,
    static_files as static_files,
    verticals as verticals,
    workbooks as workbooks,
)

"""Write operations of the service app: one operation = one transaction, with its events in the outbox.

Every check runs before the first write, so a refusal leaves no trace. Writes on a voucher sold (spend,
void, adjust) lock its row first and read its balance again afterwards: two tills on the same voucher
go one after the other and the second decides on what the first left. Writes on the services a
professional performs lock the professional's record first, so two of them never fight over the
«main service». A name two writes take at once ends in the database's unique constraint, translated
to the same 409 as the check. A write that names a row (a tax category, a category, a service, a voucher
of the catalog, a customer's card) holds it until it commits: its deletion waits for the write instead of
breaking it at the COMMIT, and one deleted meanwhile is refused as one deleted before.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    grant_sales as grant_sales,
    catalog as catalog,
    service_images as service_images,
    categories as categories,
    category_recovery as category_recovery,
    settings as settings,
    assignments as assignments,
    service_recovery as service_recovery,
    packages as packages,
    grants as grants,
    customer_reactions as customer_reactions,
    sessions as sessions,
    writes as writes,
)

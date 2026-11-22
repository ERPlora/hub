"""Input and output schemas of the service app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in minor units of the business's currency, its country's (cents in euros, whole yen in Japan; integers,
never negative; service-business-currency), and each amount's description says «in cents»: the words the assistant
reads as money (its card paints the amount in the business's currency, its instructions ask the AI for the minor
unit; test_integration_assistant.py). A percentage discount travels in basis points (1050 = 10.50 %). A
service, a category or a package is named by its id or, as a person says it (assistant, voice), by
its name; a professional by their name; a customer by their name, phone or email. Every input refuses
a field it does not declare. An edit changes only the fields it sends; on a field that may be empty
(the category, the closed price…), sending ``null`` empties it.
"""

from . import (
    assignments as assignments,
    catalog as catalog,
    categories as categories,
    customer_reactions as customer_reactions,
    fields as fields,
    grant_checks as grant_checks,
    grant_sales as grant_sales,
    grants as grants,
    movements as movements,
    packages as packages,
    recovery as recovery,
    service_images as service_images,
    sessions as sessions,
    settings as settings,
    tender as tender,
)

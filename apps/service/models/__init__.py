"""Models of the service app: the settings, the service catalog and its categories, who performs each
service, and the vouchers (the catalog's packages, the ones sold, their adjustments and sessions).

Money is in minor units of the business's currency, its country's (cents in euros, whole yen in Japan;
integers, never negative); a percentage discount in basis points (1050 = 10.50 %).
A service is archived and a category or a package deleted logically: what points at them keeps
pointing. A voucher sold (``Grant``) freezes its terms; its balance is computed when read, from its
sessions (``Redemption``) and its adjustments (``GrantAdjustment``), never stored.

One module per responsibility, each imported here so that Django registers its models, in this order.
"""

from . import (
    settings as settings,
    catalog as catalog,
    packages as packages,
    grants as grants,
)

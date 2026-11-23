"""The assistant puts a discount on an open check, or on one of its lines, only when the person speaks of that check
(SALE-F14).

Asked to lower the discount of the coffees, with a discount rule of Price lists taking 20 % off them, the model read
the open checks and put 10 % off the coffee line of table 4: nothing said the discount of a check was for a check the
person speaks of, and not the discount a product gets on every sale.
"""

import pytest
from live.assistant import description
from live.operations import get


@pytest.mark.parametrize("name", ["sale.order.set_discount", "sale.order.set_line_discount"])
def test_the_discount_of_a_check_is_of_a_check_the_person_speaks_of(name):
    assert "of an open check spoken of" in description(get(name))

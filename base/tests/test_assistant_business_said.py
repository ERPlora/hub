"""What the description of ``base.business.get``, offered in every turn, tells the model of where each datum of the
business changes: the name, the time zone and the language on erplora.com; the country never once the business is ready
(BASE-F49) and the currency never on its own, for it is the country's (BASE-F50). The model repeated «they are changed
on erplora.com» of the country and the currency too.
"""

import re

from live.assistant import description
from live.operations import get


def sentences(text: str) -> list[str]:
    return [one.strip() for one in re.split(r"(?<=[.;])\s+", text) if one.strip()]


def test_only_the_name_the_time_zone_and_the_language_are_said_to_change_on_erplora_com():
    said = sentences(description(get("base.business.get")))
    [changed_there] = [one for one in said if "changed on erplora.com" in one]
    assert all(datum in changed_there for datum in ("name", "time zone", "language"))
    assert "country" not in changed_there and "currency" not in changed_there


def test_the_country_and_the_currency_are_said_to_never_change_by_themselves():
    said = sentences(description(get("base.business.get")))
    assert any("country" in one and "no longer changes" in one for one in said)
    assert any("currency" in one and "the country's" in one and "erplora.com" not in one for one in said)

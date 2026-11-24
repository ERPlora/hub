"""What the schemas of Modifiers share: a list pages by at most 100 and an input refuses what it does not have."""

from apps.modifier.schemas.groups import GroupListIn
from apps.modifier.schemas.links import LinkListIn
from apps.modifier.schemas.options import OptionListIn

from .schema_checks import refused


def test_lists_page_by_at_most_100_and_refuse_an_unknown_filter():
    assert GroupListIn.model_validate({}).model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "name": None,
        "required": None,
        "sort": "sort_order",
    }
    assert refused(GroupListIn, limit=101) == {"limit"}
    assert refused(GroupListIn, colour="red") == {"colour"}
    assert refused(GroupListIn, sort="price") == {"sort"}
    assert refused(OptionListIn, limit=0) == {"limit"}
    assert refused(LinkListIn, offset=-1) == {"offset"}

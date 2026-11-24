"""The schemas of the till's reads: the groups of a product and the valuation of what was chosen (422 per field)."""

import uuid

from apps.modifier.schemas.till import ResolveIn, TargetIn

from .schema_checks import refused


def test_the_pos_reads_name_a_product():
    assert TargetIn.model_validate({"product": "Burger"}).product == "Burger"
    assert refused(TargetIn) == {"__all__"}
    picks = [str(uuid.uuid7()) for _ in range(3)]
    resolved = ResolveIn.model_validate(
        {"product": "Burger", "option_ids": [picks[0], picks[1], picks[0]]}
    )
    # The order of choice and the repeats are kept: they are what is valued.
    assert [str(pick) for pick in resolved.option_ids] == [picks[0], picks[1], picks[0]]
    assert ResolveIn.model_validate({"product": "Burger"}).option_ids == []
    assert refused(
        ResolveIn, product="Burger", option_ids=[str(uuid.uuid7())] * 101
    ) == {"option_ids"}

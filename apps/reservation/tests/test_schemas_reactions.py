"""The inputs of the reactions to Customers' events: they read what they need and ignore the rest of the payload."""

from apps.reservation.schemas.reactions import CustomerEventIn, MergedIn


def test_the_reactions_read_what_they_need_and_ignore_the_rest():
    merged = MergedIn.model_validate(
        {
            "id": "0192f0d4-0000-7000-8000-000000000001",
            "absorbed_id": "0192f0d4-0000-7000-8000-000000000002",
            "x": 1,
        }
    )
    assert str(merged.absorbed_id).endswith("2")
    assert CustomerEventIn.model_validate({"other": True}).id is None

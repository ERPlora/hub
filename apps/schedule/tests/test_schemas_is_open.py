"""Is it open? The moment asked about, and nothing else."""

import pytest

from apps.schedule.schemas.is_open import IsOpenIn

from .test_schemas_fields import errors


def test_is_open_takes_the_moment_and_nothing_else():
    assert IsOpenIn().when is None
    assert (
        IsOpenIn.model_validate({"when": "2026-08-18T10:00"}).when == "2026-08-18T10:00"
    )
    # The rules are read from the server, never from the caller.
    assert "business_hours" in errors(IsOpenIn, business_hours=[])


@pytest.mark.parametrize(
    "when",
    ["0001-01-01T10:00", "0001-01-01T00:30+01:00", "9999-12-31T23:30-01:00", "9999-12-31T23:30+00:00", "1899-12-31T10:00"],
)
def test_is_open_refuses_a_moment_out_of_the_calendar_under_when(when):
    assert errors(IsOpenIn, when=when) == {"when": "Choose a date between 1900 and 2200."}

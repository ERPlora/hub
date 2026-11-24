"""The row of a setting the business keeps once at most, for the command that changes it."""

from django.db import IntegrityError
from live.operations import atomic


def locked_single_row(model):
    """``model``'s only row in the business, locked until the transaction ends; made with its defaults when missing."""
    row = model.objects.select_for_update().first()
    if row is None:
        try:
            with atomic():
                row = model.objects.create()
        except IntegrityError:
            # Another request made it between the read and the insert.
            row = model.objects.select_for_update().get()
    return row

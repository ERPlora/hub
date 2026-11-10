"""What the test of an app's typed operations checks: the fields of a hand-written type of its pages
(``frontend/operations.d.ts``), to compare with its schema's (``set(schema.model_fields)``)."""

import re
from pathlib import Path


def ts_fields(interface: str, operations_ts: Path) -> set[str]:
    """The fields of ``interface`` in ``operations_ts``, its optional ones and the ones it inherits included."""
    source = operations_ts.read_text()
    found = re.search(rf"export interface {interface}(?: extends (\w+))? \{{(.*?)\n\}}", source, re.S)
    assert found, f"{interface} is not in {operations_ts}"
    fields = set(re.findall(r"^\s+(\w+)\??:", found.group(2), re.M))
    return fields | (ts_fields(found.group(1), operations_ts) if found.group(1) else set())

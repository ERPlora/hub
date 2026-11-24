"""A WORKBOOK cut at its headings, and the mark its translation keeps of each Spanish section.

The mark is the line under each heading of a translation: the hash of the section of ``WORKBOOK.md`` it was made from.
A section that falls behind is named, and two branches that change different sections change different lines of the
translation, so git merges them.
"""

import hashlib
import re
from collections.abc import Iterator
from itertools import pairwise

MARK = re.compile(r"<!-- from WORKBOOK\.md sha256:[0-9a-f]{12} -->")
_MARK_LINE = re.compile(rf"^{MARK.pattern}\n", re.MULTILINE)
_HEADING = re.compile(r"#{1,6} ")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def closes(fence: str, line: str) -> bool:
    """Whether ``line`` closes the fenced code block ``fence`` (its opening run of backticks or tildes) opened."""
    match = FENCE.match(line)
    return (
        match is not None
        and match.group(1)[0] == fence[0]
        and len(match.group(1)) >= len(fence)
        and not line.strip().lstrip(fence[0])
    )


def prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """Each line of ``text`` outside its fenced code blocks, with its number (the first is 1)."""
    fence = None
    for number, line in enumerate(text.splitlines(), start=1):
        if fence is None:
            match = FENCE.match(line)
            if match:
                fence = match.group(1)
            else:
                yield number, line
        elif closes(fence, line):
            fence = None


def sections(markdown: str) -> list[str]:
    """``markdown`` cut at each heading, of any level; what goes before the first one is a section too."""
    lines = markdown.splitlines(keepends=True)
    headings = [number - 1 for number, line in prose_lines(markdown) if _HEADING.match(line)]
    cuts = sorted({0, *headings, len(lines)})
    return ["".join(lines[start:end]) for start, end in pairwise(cuts)]


def mark(section: str) -> str:
    """The line a translation of ``section`` carries under its heading."""
    return f"<!-- from WORKBOOK.md sha256:{hashlib.sha256(section.strip().encode()).hexdigest()[:12]} -->"


def marked(source: str, body: str) -> str | None:
    """``body``, a translation of ``source``, with the mark of each section, or ``None`` when its headings are not those
    of ``source``, level by level."""
    written, translated = sections(source), sections(body)
    if _levels(written) != _levels(translated):
        return None
    parts = []
    for section, translation in zip(written, translated, strict=True):
        heading, _, text = translation.partition("\n")
        parts.append(f"{heading}\n{mark(section)}\n{text}")
    return "".join(parts)


def _levels(parts: list[str]) -> list[int]:
    """The level of each section's heading; 0 without one."""
    return [match.end() if (match := _HEADING.match(part)) else 0 for part in parts]


def current_body(source: str, text: str) -> str | None:
    """``text``, a translation, without its marks while they are those of ``source``, else ``None``."""
    body = _MARK_LINE.sub("", text)
    return body if marked(source, body) == text else None


def behind(source: str, text: str) -> list[str]:
    """The heading of each section of ``source`` whose mark ``text`` does not carry, with the mark to write."""
    return [
        f"{section.partition('\n')[0]} → {line}" for section in sections(source) if (line := mark(section)) not in text
    ]

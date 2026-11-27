"""The help of an app (``base.help.get``), a module's or the Hub's own screens': what goes in and what comes out."""

from ninja import Schema
from pydantic import Field

from base.schemas.assistant import ReadOn


class AppHelpIn(Schema):
    """``base.help.get``: the app whose help is asked for."""

    app: str = Field(
        max_length=100,
        description=(
            "The app's id, as its screens' addresses start (e.g. «table»), or «base» for the Hub's own screens (Home, "
            "Employees, Files, Apps, System, Settings, My profile)."
        ),
    )
    offset: ReadOn = 0


class HelpScreenOut(Schema):
    """One tab of the module (its menu entry) or one of the Hub's own screens the person can see (its route, the
    parameters unread, with the hash of its tab) and, in ``text``, the summary of its section of the WORKBOOK (what goes
    before the section's first window), in markdown."""

    id: str
    title: str
    path: str
    text: str


class HelpFlowOut(Schema):
    """How a task is done: its title, the tabs or screens it happens on, its steps and what happens if it fails, in
    markdown; ``videos``, the YouTube video ids of its short videos, none when it has no videos. Of the Hub's own screens,
    only what the person may do."""

    id: str
    title: str
    screens: list[str]
    steps: str
    failure: str
    videos: list[str]


class AppHelpOut(Schema):
    """The app's help in ``language``, the person's own or else the WORKBOOK's source language; ``video`` is the
    YouTube video id of the app, when it has one."""

    app: str
    name: str
    language: str
    video: str | None
    purpose: str
    screens: list[HelpScreenOut]
    flows: list[HelpFlowOut]

"""The help window of a module (``base.help.get``): what goes in and what comes out."""

from ninja import Schema
from pydantic import Field


class AppHelpIn(Schema):
    """``base.help.get``: the module whose help the window shows."""

    app: str = Field(max_length=100, description="The module's id, as its screens' addresses start (e.g. «table»).")


class HelpScreenOut(Schema):
    """One tab of the module: its menu entry and, in ``text``, the summary of its section of the WORKBOOK (what goes
    before the section's first window), in markdown."""

    id: str
    title: str
    path: str
    text: str


class HelpFlowOut(Schema):
    """How a task is done: its title, the tabs it happens on, its steps and what happens if it fails, in markdown."""

    id: str
    title: str
    screens: list[str]
    steps: str
    failure: str


class AppHelpOut(Schema):
    """The module's help in ``language``, the person's own or else the WORKBOOK's source language; ``video`` is the
    YouTube video id of the module, when it has one."""

    app: str
    name: str
    language: str
    video: str | None
    purpose: str
    screens: list[HelpScreenOut]
    flows: list[HelpFlowOut]

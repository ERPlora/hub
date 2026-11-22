"""The short videos the help window (``base.help.get``) shows in each task of a module, for the tests of the modules
that declare them (``Help.flow_videos``)."""

from live.context import OperationContext
from live.operations import get

from base.schemas.app_help import AppHelpIn
from base.tenancy.tests.business import A

#: The column of each language in a table of videos: the flows a video shows, then its Spanish and its English id.
COLUMNS = {"es": 1, "en": 2}


def shown(app: str, language: str) -> dict[str, list[str]]:
    """Each task of ``app``'s help window that shows videos to a person who reads ``language``, with their ids."""
    ctx = OperationContext(scope=A, actor="ana", permissions=frozenset({"base.view_home"}), language=language)
    return {flow.id: flow.videos for flow in get("base.help.get")(ctx, AppHelpIn(app=app)).flows if flow.videos}


def by_task(videos: list[tuple[tuple[str, ...], str, str]], language: str) -> dict[str, list[str]]:
    """``videos`` turned into each flow's ids in ``language``, in the table's order when a flow has more than one."""
    tasks: dict[str, list[str]] = {}
    for video in videos:
        for flow in video[0]:
            tasks.setdefault(flow, []).append(video[COLUMNS[language]])
    return tasks

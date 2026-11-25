"""The modules' counters of the bell (``bell``) and how often the bell reads them again."""

from collections.abc import Iterable, Mapping

from django.core import checks
from live.context import OperationContext
from live.meta import all_live_app_configs, LiveAppConfig

from base import bell
from base.home.module_hooks import hook_failed, run_hook

#: The attribute of a module's ``LiveAppConfig`` with how often the bell reads its counters again: key → seconds.
BELL_REFRESH_ATTRIBUTE = "bell_refresh_every"


#: The shortest of those periods: the old hub's bell asked every 30 s, and a shorter one would make every open screen
#: of the business a poller of its hub.
MIN_BELL_REFRESH_SECONDS = 30


def bell_counters(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[dict]:
    """The modules' counters of the bell above zero that the person of ``ctx`` may see."""
    counters = []
    for config in configs:
        for counter in config.bell:
            if not ctx.has(counter.permission):
                continue
            key = f"{config.label}.{counter.key}"
            try:
                notice = bell.notice(key, counter, run_hook(ctx, counter.operation, counter.params))
            except Exception:
                hook_failed(key, counter.operation)
                continue
            if notice["count"] > 0:
                counters.append(notice)
    return counters


def bell_refresh_every(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> int | None:
    """How often the bell of the person of ``ctx`` reads its counters again: the shortest period declared for a counter
    they may see (at zero too: it is the time that raises it), ``None`` when none asks (its events only, as before)."""
    periods = [
        seconds
        for config in configs
        for key, seconds in (getattr(config, BELL_REFRESH_ATTRIBUTE, None) or {}).items()
        for counter in config.bell
        if counter.key == key and ctx.has(counter.permission)
    ]
    return min(periods, default=None)


def bell_refresh_errors(configs: Iterable[LiveAppConfig]) -> list[checks.CheckMessage]:
    """``base.E007``: ``bell_refresh_every`` maps counters of the app's own bell to whole seconds, none under
    :data:`MIN_BELL_REFRESH_SECONDS`."""
    hint = (
        f"Declare {BELL_REFRESH_ATTRIBUTE} = {{\"<counter key>\": <seconds>}} on the module's LiveAppConfig, for counters of "
        f"its own bell that change as time passes, each at least {MIN_BELL_REFRESH_SECONDS} s."
    )
    errors = []
    for config in configs:
        declared = getattr(config, BELL_REFRESH_ATTRIBUTE, None)
        if declared is None:
            continue
        problems = []
        if not isinstance(declared, Mapping):
            problems.append(f"is {declared!r}, not a mapping of its counters to seconds")
        else:
            counters = {counter.key for counter in getattr(config, "bell", [])}
            for key, seconds in declared.items():
                if key not in counters:
                    problems.append(f"names {key!r}, which is no counter of its bell")
                elif not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < MIN_BELL_REFRESH_SECONDS:
                    problems.append(f"reads {key!r} again every {seconds!r}, not whole seconds from {MIN_BELL_REFRESH_SECONDS}")
        errors += [
            checks.Error(f"{config.label}'s {BELL_REFRESH_ATTRIBUTE} {problem}.", hint=hint, obj=config, id="base.E007")
            for problem in problems
        ]
    return errors


@checks.register("base")
def check_bell_refresh(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """The bell's clock of every app of ours (whatever ``app_configs`` ``manage.py check`` passes)."""
    return bell_refresh_errors(all_live_app_configs())

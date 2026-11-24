"""A period on an assistant's card, from its start to its end, as the person's language writes an interval (CLDR, by
Babel's ``format_interval``): two days «21–31 dic 2026», two hours «14:00–15:00», two moments of a day «26 nov 2026,
14:00–15:00». A moment of another zone is said at the business's hour, as the card says one alone."""

import datetime as dt

from babel import Locale
from babel.dates import format_date, format_interval, format_time, get_datetime_format

from base.business import babel_locale, business_zone

Moment = dt.date | dt.time | dt.datetime


def period(start: Moment, end: Moment, language: str) -> str:
    locale = babel_locale(language)
    if isinstance(start, dt.datetime) and isinstance(end, dt.datetime):
        return _moments(_here(start), _here(end), locale)
    if isinstance(start, dt.time):
        return format_interval(start, end, _hours(locale), locale=locale)
    return format_interval(start, end, "yMMMd", locale=locale)


def _here(moment: dt.datetime) -> dt.datetime:
    return moment.astimezone(business_zone()).replace(tzinfo=None) if moment.tzinfo else moment


def _hours(locale: Locale) -> str:
    """The hours as the language's short time writes them: on a 12-hour clock or on a 24-hour one."""
    return "hm" if "h" in locale.time_formats["short"].pattern else "Hm"


def _moments(start: dt.datetime, end: dt.datetime, locale: Locale) -> str:
    joined = get_datetime_format("medium", locale=locale)
    day = format_date(start.date(), "medium", locale=locale)
    if start.date() == end.date():
        hours = format_interval(start.time(), end.time(), _hours(locale), locale=locale)
        return joined.replace("{1}", day).replace("{0}", hours)
    ends = joined.replace("{1}", format_date(end.date(), "medium", locale=locale))
    starts = joined.replace("{1}", day).replace("{0}", format_time(start.time(), "short", locale=locale))
    ends = ends.replace("{0}", format_time(end.time(), "short", locale=locale))
    return locale.interval_formats[None].replace("{0}", starts).replace("{1}", ends)

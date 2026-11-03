"""Google reviews of a hub's place: the rating, the count and up to five reviews of the business on Google Maps.

The owner pastes in the editor the link of the business on Google Maps (the address bar's, or the «Share» button's
``maps.app.goo.gl`` link) or its Place ID (:func:`parse`). The Hub asks Google itself, from the server, with the
platform's key (``settings.GOOGLE_PLACES_API_KEY``): the visitor's browser never talks to Google (the public page's CSP
allows no third party) and no Google script runs on it. Places API (New), with ``httpx`` (5 s at most per call):

- a Place ID, or a link that carries one (``place_id=``, ``query_place_id=``, ``q=place_id:``, ``!19s``), is used as is;
- a ``/maps/place/<name>/@<lat>,<lng>`` link (or ``/maps/search/<text>/``, ``q=<text>``, ``query=<text>``) is
  searched by its name and the site's address with **Text Search**
  (``POST https://places.googleapis.com/v1/places:searchText``, field mask ``places.id``: the «IDs only» request,
  which Google does not bill), biased to the link's point, and the first place found is taken;
- a share link is followed once (its redirect is the ``/maps/place/`` link it stands for);
- then **Place Details** (``GET https://places.googleapis.com/v1/places/{id}``, field mask
  ``id,displayName,rating,userRatingCount,reviews,googleMapsUri``; billed as «Place Details Enterprise + Atmosphere»):
  the rating, the count, the link to the place and up to five reviews (most relevant first), each with its author and
  its text in the language it was written in (``originalText``), never changed here.

What Google answered is kept in the cache a day per hub and place (``website:reviews:<slug>:<place id>``), and the
place a name or a share link led to as long (``website:place:…``). A failure (no answer in 5 s, a refused key, a
place not found, an answer that is no place) is logged and kept 10 minutes under the same key (:data:`FAILED`), so a
broken key or link never hammers Google; one process asks at a time (``website:reviews-lock:…``). Without the key,
nothing is asked and nothing is kept.

:func:`load` reads the cache and asks Google only when it holds nothing; :func:`read` and :func:`state` never ask
(the public API, the preview and the editor). The site keeps its last good answer in its row (``Site.reviews_snapshot``,
written by ``services``): a flushed cache or a failure still shows it, for 30 days at most and only for its own place.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, quote, unquote_plus, urlsplit

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

PLACES_URL = "https://places.googleapis.com/v1/places"
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
#: What Place Details is asked for (the field mask decides what Google bills).
DETAILS_FIELDS = "id,displayName,rating,userRatingCount,reviews,googleMapsUri"
#: Text Search is asked for the place's id only («IDs only», not billed).
SEARCH_FIELDS = "places.id"
#: How close to the link's point the search looks first, in metres.
SEARCH_RADIUS = 1000.0
TIMEOUT = httpx.Timeout(5.0)
#: How long Google's answer is kept: a day.
TTL = 24 * 3600
#: How long a failure is kept before Google is asked again: 10 minutes.
FAILURE_TTL = 600
#: How long one process may hold the right to ask Google for a place.
LOCK_TTL = 30
#: How long the site's last good answer may stand in for Google's.
MAX_SNAPSHOT_AGE = timedelta(days=30)
#: The cache's mark of a failure.
FAILED = "failed"
#: The most reviews Google sends, and the page shows.
MAX_REVIEWS = 5
MAX_AUTHOR = 120
MAX_TEXT = 4000

#: A Place ID as the owner may paste it (an establishment's starts with «ChIJ»).
_PLACE_ID = re.compile(r"^ChIJ[A-Za-z0-9_-]{10,250}$")
#: A Place ID inside a link.
_PLACE_ID_IN_LINK = re.compile(r"^[A-Za-z0-9_-]{10,250}$")
_DATA_PLACE_ID = re.compile(r"!19s(ChIJ[A-Za-z0-9_-]{10,250})")
_POINT = re.compile(r"/@(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)")
_GOOGLE_HOST = re.compile(r"^(?:www\.)?google\.[a-z]{2,3}(?:\.[a-z]{2})?$")
_MAPS_HOST = re.compile(r"^maps\.google\.[a-z]{2,3}(?:\.[a-z]{2})?$")
_UNSAFE = set("\"'<>`\\")


class PlacesError(Exception):
    """Google did not give a usable place: the message says why (for the log)."""


@dataclass(frozen=True)
class PlaceRef:
    """What the owner's input says about the place: its id, or its name (and point) to search, or a share link."""

    place_id: str = ""
    name: str = ""
    near: tuple[float, float] | None = None
    short_url: str = ""


def parse(ref: str) -> PlaceRef:
    """The place ``ref`` names: a Place ID, a Google Maps link to a place or a Maps share link; ``ValueError`` for
    anything else (a plain name, another site, a map without a place)."""
    ref = ref.strip()
    if _PLACE_ID.match(ref):
        return PlaceRef(place_id=ref)
    parts = urlsplit(ref)
    if parts.scheme != "https" or not parts.netloc or any(char.isspace() or char in _UNSAFE for char in ref):
        raise ValueError("not a https link")
    host, path = parts.netloc.lower(), parts.path
    if (host == "maps.app.goo.gl" and path.strip("/")) or (host == "goo.gl" and path.startswith("/maps/") and path[6:]):
        return PlaceRef(short_url=ref)
    if not (_MAPS_HOST.match(host) or (_GOOGLE_HOST.match(host) and path.startswith("/maps"))):
        raise ValueError("not a Google Maps link")
    query = parse_qs(parts.query)
    for found in (*query.get("place_id", []), *query.get("query_place_id", [])):
        if _PLACE_ID_IN_LINK.match(found):
            return PlaceRef(place_id=found)
    for found in query.get("q", []):
        if found.startswith("place_id:") and _PLACE_ID_IN_LINK.match(found.removeprefix("place_id:")):
            return PlaceRef(place_id=found.removeprefix("place_id:"))
    in_data = _DATA_PLACE_ID.search(path)
    if in_data:
        return PlaceRef(place_id=in_data.group(1))
    for prefix in ("/maps/place/", "/maps/search/"):
        name = unquote_plus(path.removeprefix(prefix).split("/", 1)[0]).strip() if path.startswith(prefix) else ""
        if name:
            point = _POINT.search(path)
            near = (float(point.group(1)), float(point.group(2))) if point else None
            return PlaceRef(name=name, near=near)
    # A search by name and address (where the app's share links lead, and the Maps URLs' ``query=``).
    for found in (*query.get("q", []), *query.get("query", [])):
        if found.strip():
            return PlaceRef(name=found.strip())
    raise ValueError("a Google Maps link without a place")


def configured() -> bool:
    """Whether this server may ask Google (the platform's key is set)."""
    return bool(settings.GOOGLE_PLACES_API_KEY)


# The cache


def _digest(ref: str, address: list[str]) -> str:
    return hashlib.sha256("\n".join([ref.strip(), *address]).encode()).hexdigest()[:32]


def reviews_key(slug: str, place_id: str) -> str:
    """Google's answer for ``place_id`` on ``slug``. The slug is the hash tag (``{<slug>}``) of this key and
    :func:`resolution_key`'s: :func:`forget` drops both in one call, which the Valkey cluster accepts only for keys of
    one slot (``base/cache.py``)."""
    return f"website:reviews:{{{slug}}}:{place_id}"


def resolution_key(slug: str, ref: str, address: list[str]) -> str:
    """Where the place a name or a share link led to is kept (it depends on the address the search used too)."""
    return f"website:place:{{{slug}}}:{_digest(ref, address)}"


def lock_key(slug: str, ref: str, address: list[str]) -> str:
    return f"website:reviews-lock:{slug}:{_digest(ref, address)}"


def known_place_id(slug: str, ref: str, address: list[str]) -> str:
    """The Place ID of ``ref`` without asking Google: in the input itself, or found before; ``""`` otherwise."""
    try:
        place = parse(ref)
    except ValueError:
        return ""
    if place.place_id:
        return place.place_id
    found = cache.get(resolution_key(slug, ref, address))
    return found if found and found != FAILED else ""


def cached(slug: str, ref: str, address: list[str]) -> dict | str | None:
    """What is kept for ``ref`` on ``slug``: Google's answer, :data:`FAILED`, or ``None`` when nothing is."""
    place_id = known_place_id(slug, ref, address)
    if place_id:
        return cache.get(reviews_key(slug, place_id))
    return FAILED if cache.get(resolution_key(slug, ref, address)) == FAILED else None


def forget(slug: str, ref: str, address: list[str]) -> None:
    """Drop what is kept for ``ref`` on ``slug`` (its answer or failure, and the place it led to)."""
    place_id = known_place_id(slug, ref, address)
    cache.delete_many(
        [resolution_key(slug, ref, address)] + ([reviews_key(slug, place_id)] if place_id else [])
    )


# Reading without asking


def usable_snapshot(snapshot: dict | None, ref: str, place_id: str) -> dict | None:
    """The site's last good answer, when it is of this place (by its id, or by the same input) and younger than 30
    days."""
    if not snapshot or not snapshot.get("place_id"):
        return None
    if snapshot["place_id"] != place_id and snapshot.get("place_ref") != ref.strip():
        return None
    try:
        fetched = datetime.fromisoformat(snapshot.get("fetched_at", ""))
    except ValueError:
        return None
    return snapshot if timezone.now() - fetched <= MAX_SNAPSHOT_AGE else None


def read(slug: str, ref: str, address: list[str], snapshot: dict | None) -> dict | None:
    """The reviews to show for ``ref`` without asking Google: the day's answer, else the site's last good one."""
    if not ref.strip():
        return None
    found = cached(slug, ref, address)
    if isinstance(found, dict):
        return found
    return usable_snapshot(snapshot, ref, known_place_id(slug, ref, address))


def state(slug: str, ref: str, address: list[str], snapshot: dict | None) -> tuple[str, dict | None]:
    """What the editor says about ``ref``: ``empty`` (no input), ``ready`` (reviews to show), ``unavailable`` (this
    server has no key), ``failed`` (Google's last answer was a failure) or ``waiting`` (not asked yet)."""
    if not ref.strip():
        return "empty", None
    shown = read(slug, ref, address, snapshot)
    if shown is not None:
        return "ready", shown
    if not configured():
        return "unavailable", None
    return ("failed" if cached(slug, ref, address) == FAILED else "waiting"), None


# Asking Google


def load(slug: str, ref: str, address: list[str]) -> dict | None:
    """Google's answer for ``ref`` on ``slug``: the cache's, or asked now (at most 5 s a call) and kept; ``None`` when
    there is none (a failure, kept 10 minutes; no key; another process asking right now)."""
    found = cached(slug, ref, address)
    if found is not None:
        return found if isinstance(found, dict) else None
    if not ref.strip() or not configured():
        return None
    lock = lock_key(slug, ref, address)
    if not cache.add(lock, 1, LOCK_TTL):
        return None
    try:
        with httpx.Client(timeout=TIMEOUT) as http:
            return _ask(http, slug, ref, address)
    finally:
        cache.delete(lock)


def _ask(http: httpx.Client, slug: str, ref: str, address: list[str]) -> dict | None:
    known = known_place_id(slug, ref, address)
    place_id = known
    try:
        if not known:
            place_id = _find(http, parse(ref), address)
            cache.set(resolution_key(slug, ref, address), place_id, TTL)
        payload = _payload(_details(http, place_id), place_id, ref)
    except (httpx.HTTPError, PlacesError, ValueError) as error:
        logger.warning("website: Google Places gave no reviews for hub %s (%s): %s", slug, ref, error)
        key = reviews_key(slug, place_id) if place_id else resolution_key(slug, ref, address)
        cache.set(key, FAILED, FAILURE_TTL)
        return None
    cache.set(reviews_key(slug, place_id), payload, TTL)
    return payload


def _headers(fields: str) -> dict[str, str]:
    return {"X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY, "X-Goog-FieldMask": fields}


def _find(http: httpx.Client, place: PlaceRef, address: list[str], *, followed: bool = False) -> str:
    """The Place ID of ``place``: a share link's target, or the first place Text Search finds for its name."""
    if place.place_id:
        return place.place_id
    if place.short_url:
        if followed:
            raise PlacesError("a share link that leads to another share link")
        response = http.get(place.short_url, follow_redirects=False)
        location = response.headers.get("Location", "")
        if not response.is_redirect or not location:
            raise PlacesError(f"the share link answered {response.status_code} without a redirect")
        return _find(http, parse(location), address, followed=True)
    body: dict[str, Any] = {"textQuery": ", ".join([place.name, *address]), "pageSize": 1}
    if place.near:
        latitude, longitude = place.near
        body["locationBias"] = {
            "circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": SEARCH_RADIUS}
        }
    response = http.post(SEARCH_URL, json=body, headers=_headers(SEARCH_FIELDS))
    if response.status_code != 200:
        raise PlacesError(f"Text Search answered {response.status_code}")
    places = _json_object(response).get("places") or []
    found = places[0].get("id", "") if isinstance(places, list) and places and isinstance(places[0], dict) else ""
    if not isinstance(found, str) or not _PLACE_ID_IN_LINK.match(found):
        raise PlacesError("Text Search found no place")
    return found


def _details(http: httpx.Client, place_id: str) -> dict:
    response = http.get(f"{PLACES_URL}/{quote(place_id, safe='')}", headers=_headers(DETAILS_FIELDS))
    if response.status_code != 200:
        raise PlacesError(f"Place Details answered {response.status_code}")
    return _json_object(response)


def _json_object(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        raise PlacesError("an answer that is not JSON") from None
    if not isinstance(data, dict):
        raise PlacesError("an answer that is not a JSON object")
    return data


def _https(value: Any) -> str:
    """``value`` when it is a ``https://`` link that cannot break out of an attribute, else ``""``."""
    if not isinstance(value, str):
        return ""
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or any(char.isspace() or char in _UNSAFE for char in value):
        return ""
    return value


def _text(value: Any) -> str:
    return value.get("text", "") if isinstance(value, dict) and isinstance(value.get("text"), str) else ""


def _payload(place: dict, place_id: str, ref: str) -> dict:
    """Google's place as the site keeps it: what the page shows, nothing more."""
    rating = place.get("rating")
    count = place.get("userRatingCount")
    reviews = []
    for review in place.get("reviews") or []:
        if not isinstance(review, dict) or len(reviews) == MAX_REVIEWS:
            continue
        stars = review.get("rating")
        if not isinstance(stars, int | float) or not 1 <= stars <= 5:
            continue
        author = review.get("authorAttribution") if isinstance(review.get("authorAttribution"), dict) else {}
        reviews.append(
            {
                "author": str(author.get("displayName") or "")[:MAX_AUTHOR],
                "author_uri": _https(author.get("uri")),
                "rating": round(stars),
                "text": (_text(review.get("originalText")) or _text(review.get("text"))).strip()[:MAX_TEXT],
                "time": review.get("publishTime") if isinstance(review.get("publishTime"), str) else "",
                "uri": _https(review.get("googleMapsUri")),
            }
        )
    return {
        "place_id": place_id,
        "place_ref": ref.strip(),
        "name": _text(place.get("displayName"))[:MAX_AUTHOR],
        "rating": float(rating) if isinstance(rating, int | float) and 1 <= rating <= 5 else None,
        "count": int(count) if isinstance(count, int) and count >= 0 else 0,
        "maps_uri": _https(place.get("googleMapsUri")),
        "reviews": reviews,
        "fetched_at": timezone.now().isoformat(),
    }

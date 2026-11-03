"""Google reviews of a hub's place (``apps.website.reviews``): the owner's link or Place ID read into a place, Google's
Places API (New) asked from the server (Text Search to find a place by its name, Place Details for its rating and
reviews), the answer kept 24 hours per hub and place and a failure 10 minutes, so a broken key never hammers Google.

``respx`` stands in for the transport only: what is checked is the request the Hub writes and how each answer is
read. Nothing here reaches Google.
"""

import json
from datetime import timedelta

import httpx
import pytest
import respx
from django.core.cache import cache
from django.utils import timezone

from apps.website import reviews

KEY = "test-places-key"
SLUG = "a"
PLACE = "ChIJN1t_tDeuEmsRUsoyG83frY4"
DETAILS = f"https://places.googleapis.com/v1/places/{PLACE}"
SEARCH = "https://places.googleapis.com/v1/places:searchText"
ADDRESS = ["Calle Mayor 1", "28013 Madrid"]
NAME_LINK = (
    "https://www.google.com/maps/place/Peluquer%C3%ADa+Manoli/@40.4167754,-3.7037902,17z/"
    "data=!3m1!4b1!4m6!3m5!1s0xd42287e472b3b8f:0x6a4f71889c7d3c2b!8m2!3d40.4167754!4d-3.7037902"
)


def google_place(**overrides) -> dict:
    """Place Details as Google answers it for the field mask the Hub asks."""
    place = {
        "id": PLACE,
        "displayName": {"text": "Peluquería Manoli", "languageCode": "es"},
        "rating": 4.7,
        "userRatingCount": 128,
        "googleMapsUri": "https://maps.google.com/?cid=7660264463346408491",
        "reviews": [
            {
                "name": f"places/{PLACE}/reviews/r{index}",
                "relativePublishTimeDescription": "2 months ago",
                "rating": 5 - index % 2,
                "text": {"text": f"Translated {index}", "languageCode": "en"},
                "originalText": {"text": f"  Me encanta, número {index}  ", "languageCode": "es"},
                "authorAttribution": {
                    "displayName": f"Cliente {index}",
                    "uri": f"https://www.google.com/maps/contrib/{index}",
                    "photoUri": f"https://lh3.googleusercontent.com/a/{index}",
                },
                "publishTime": "2026-08-20T10:00:00Z",
                "googleMapsUri": f"https://www.google.com/maps/reviews/data=r{index}",
            }
            for index in range(6)
        ],
    }
    place.update(overrides)
    return place


@pytest.fixture(autouse=True)
def places_key(settings):
    settings.GOOGLE_PLACES_API_KEY = KEY


@pytest.fixture
def cache_writes(monkeypatch):
    """Every ``cache.set`` of the module: (key, value, timeout)."""
    writes = []
    real = cache.set

    def recording(key, value, timeout=None, **kwargs):
        writes.append((key, value, timeout))
        return real(key, value, timeout, **kwargs)

    monkeypatch.setattr(reviews.cache, "set", recording)
    return writes


# The owner's input


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (PLACE, reviews.PlaceRef(place_id=PLACE)),
        (f"  {PLACE}  ", reviews.PlaceRef(place_id=PLACE)),
        (f"https://www.google.com/maps/place/?q=place_id:{PLACE}", reviews.PlaceRef(place_id=PLACE)),
        (f"https://www.google.com/maps/search/?api=1&query=Manoli&query_place_id={PLACE}", reviews.PlaceRef(place_id=PLACE)),
        (f"https://maps.google.es/maps?place_id={PLACE}", reviews.PlaceRef(place_id=PLACE)),
        (f"https://www.google.com/maps/place/Manoli/data=!4m2!3m1!19s{PLACE}", reviews.PlaceRef(place_id=PLACE)),
        (NAME_LINK, reviews.PlaceRef(name="Peluquería Manoli", near=(40.4167754, -3.7037902))),
        ("https://www.google.es/maps/place/Bar+Pepe/", reviews.PlaceRef(name="Bar Pepe")),
        # Where the app's share links lead: a search for the place by its name and address.
        ("https://maps.google.com/?q=Peluquer%C3%ADa+Manoli,+Calle+Mayor+1&ftid=0xd42:0x6a4", reviews.PlaceRef(name="Peluquería Manoli, Calle Mayor 1")),
        ("https://www.google.com/maps/search/Bar+Pepe+Madrid/@40.41,-3.70,15z", reviews.PlaceRef(name="Bar Pepe Madrid", near=(40.41, -3.70))),
        ("https://maps.app.goo.gl/AbCdEf123", reviews.PlaceRef(short_url="https://maps.app.goo.gl/AbCdEf123")),
        ("https://goo.gl/maps/AbCdEf123", reviews.PlaceRef(short_url="https://goo.gl/maps/AbCdEf123")),
    ],
)
def test_a_place_id_a_maps_link_or_a_share_link_is_read(ref, expected):
    assert reviews.parse(ref) == expected


@pytest.mark.parametrize(
    "ref",
    [
        "Peluquería Manoli",
        "ChIJshort",
        f"http://www.google.com/maps/place/?q=place_id:{PLACE}",
        "https://evil.example/maps/place/Manoli/",
        "https://www.google.com/maps/@40.41,-3.70,15z",
        "https://www.google.com/maps/place//@40.41,-3.70,15z",
        "https://www.google.com/search?q=manoli",
        "https://maps.app.goo.gl/",
        f'https://www.google.com/maps/place/?q=place_id:{PLACE}"><script>',
    ],
)
def test_anything_else_is_refused(ref):
    with pytest.raises(ValueError):
        reviews.parse(ref)


# Asking Google


@respx.mock
def test_a_place_id_is_asked_to_place_details_with_the_key_and_the_field_mask_and_kept_a_day(cache_writes):
    route = respx.get(DETAILS).mock(return_value=httpx.Response(200, json=google_place()))
    payload = reviews.load(SLUG, PLACE, ADDRESS)
    request = route.calls.last.request
    assert request.headers["X-Goog-Api-Key"] == KEY
    assert request.headers["X-Goog-FieldMask"] == "id,displayName,rating,userRatingCount,reviews,googleMapsUri"
    assert payload["place_id"] == PLACE and payload["place_ref"] == PLACE
    assert (payload["name"], payload["rating"], payload["count"]) == ("Peluquería Manoli", 4.7, 128)
    assert payload["maps_uri"] == "https://maps.google.com/?cid=7660264463346408491"
    # At most five, as Google sends them; the text in its own language, as written (only its spaces trimmed).
    assert len(payload["reviews"]) == 5
    assert payload["reviews"][0] == {
        "author": "Cliente 0",
        "author_uri": "https://www.google.com/maps/contrib/0",
        "rating": 5,
        "text": "Me encanta, número 0",
        "time": "2026-08-20T10:00:00Z",
        "uri": "https://www.google.com/maps/reviews/data=r0",
    }
    assert payload["fetched_at"]
    assert cache_writes == [(f"website:reviews:{{{SLUG}}}:{PLACE}", payload, 24 * 3600)]
    # Within the day, Google is not asked again.
    assert reviews.load(SLUG, PLACE, ADDRESS) == payload
    assert route.call_count == 1


@respx.mock
def test_a_link_by_name_is_found_with_text_search_near_its_point_and_the_address():
    search = respx.post(SEARCH).mock(return_value=httpx.Response(200, json={"places": [{"id": PLACE}]}))
    respx.get(DETAILS).mock(return_value=httpx.Response(200, json=google_place()))
    payload = reviews.load(SLUG, NAME_LINK, ADDRESS)
    request = search.calls.last.request
    assert request.headers["X-Goog-Api-Key"] == KEY
    # Only the id: Text Search's «IDs only», which Google does not bill.
    assert request.headers["X-Goog-FieldMask"] == "places.id"
    assert json.loads(request.content) == {
        "textQuery": "Peluquería Manoli, Calle Mayor 1, 28013 Madrid",
        "pageSize": 1,
        "locationBias": {"circle": {"center": {"latitude": 40.4167754, "longitude": -3.7037902}, "radius": 1000.0}},
    }
    assert payload["place_id"] == PLACE and payload["place_ref"] == NAME_LINK
    # The place found is kept: the next read knows it without searching.
    assert reviews.known_place_id(SLUG, NAME_LINK, ADDRESS) == PLACE
    assert reviews.load(SLUG, NAME_LINK, ADDRESS) == payload
    assert search.call_count == 1


@respx.mock
def test_a_share_link_is_followed_once_to_the_maps_link_it_stands_for():
    short = respx.get("https://maps.app.goo.gl/AbCdEf123").mock(
        return_value=httpx.Response(302, headers={"Location": NAME_LINK})
    )
    respx.post(SEARCH).mock(return_value=httpx.Response(200, json={"places": [{"id": PLACE}]}))
    respx.get(DETAILS).mock(return_value=httpx.Response(200, json=google_place()))
    payload = reviews.load(SLUG, "https://maps.app.goo.gl/AbCdEf123", ADDRESS)
    assert payload["place_id"] == PLACE
    assert short.call_count == 1


@respx.mock
def test_a_share_link_that_leads_elsewhere_is_a_failure():
    respx.get("https://maps.app.goo.gl/AbCdEf123").mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/"})
    )
    assert reviews.load(SLUG, "https://maps.app.goo.gl/AbCdEf123", ADDRESS) is None
    assert reviews.cached(SLUG, "https://maps.app.goo.gl/AbCdEf123", ADDRESS) == reviews.FAILED


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED"}}),
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["not", "a", "place"]),
        httpx.ConnectTimeout("too slow"),
        httpx.ReadTimeout("too slow"),
    ],
)
@respx.mock
def test_a_failure_is_kept_ten_minutes_so_google_is_not_asked_again_meanwhile(answer, cache_writes, caplog):
    route = respx.get(DETAILS)
    if isinstance(answer, Exception):
        route.mock(side_effect=answer)
    else:
        route.mock(return_value=answer)
    assert reviews.load(SLUG, PLACE, ADDRESS) is None
    assert cache_writes == [(f"website:reviews:{{{SLUG}}}:{PLACE}", reviews.FAILED, 600)]
    assert reviews.cached(SLUG, PLACE, ADDRESS) == reviews.FAILED
    assert reviews.load(SLUG, PLACE, ADDRESS) is None
    assert route.call_count == 1
    assert "Google Places" in caplog.text and SLUG in caplog.text


@respx.mock
def test_a_name_google_does_not_find_is_a_failure_kept_ten_minutes(cache_writes):
    search = respx.post(SEARCH).mock(return_value=httpx.Response(200, json={}))
    assert reviews.load(SLUG, NAME_LINK, ADDRESS) is None
    assert [timeout for _key, value, timeout in cache_writes if value == reviews.FAILED] == [600]
    assert reviews.cached(SLUG, NAME_LINK, ADDRESS) == reviews.FAILED
    assert reviews.load(SLUG, NAME_LINK, ADDRESS) is None
    assert search.call_count == 1


@respx.mock
def test_without_the_platforms_key_google_is_never_asked_and_nothing_is_kept(settings, cache_writes):
    settings.GOOGLE_PLACES_API_KEY = ""
    route = respx.get(DETAILS).mock(return_value=httpx.Response(200, json=google_place()))
    assert reviews.configured() is False
    assert reviews.load(SLUG, PLACE, ADDRESS) is None
    assert route.call_count == 0 and cache_writes == []


@respx.mock
def test_while_another_process_asks_google_this_one_does_not():
    route = respx.get(DETAILS).mock(return_value=httpx.Response(200, json=google_place()))
    assert cache.add(reviews.lock_key(SLUG, PLACE, ADDRESS), 1, 30)
    assert reviews.load(SLUG, PLACE, ADDRESS) is None
    assert route.call_count == 0
    cache.delete(reviews.lock_key(SLUG, PLACE, ADDRESS))
    assert reviews.load(SLUG, PLACE, ADDRESS)["place_id"] == PLACE


@respx.mock
def test_a_link_google_sends_that_is_not_https_is_dropped():
    place = google_place(googleMapsUri="javascript:alert(1)")
    place["reviews"][0]["authorAttribution"]["uri"] = "http://example.com/"
    place["reviews"][1]["googleMapsUri"] = 'https://x.example/"><script>'
    respx.get(DETAILS).mock(return_value=httpx.Response(200, json=place))
    payload = reviews.load(SLUG, PLACE, ADDRESS)
    assert payload["maps_uri"] == ""
    assert payload["reviews"][0]["author_uri"] == ""
    assert payload["reviews"][1]["uri"] == ""


@respx.mock
def test_a_place_without_rating_or_reviews_is_kept_as_it_is():
    respx.get(DETAILS).mock(return_value=httpx.Response(200, json={"id": PLACE, "displayName": {"text": "Nuevo"}}))
    payload = reviews.load(SLUG, PLACE, ADDRESS)
    assert (payload["rating"], payload["count"], payload["reviews"]) == (None, 0, [])


# Reading what is kept (no network)


def good(place_ref=PLACE, place_id=PLACE, age=timedelta(0)) -> dict:
    return {
        "place_id": place_id,
        "place_ref": place_ref,
        "name": "Peluquería Manoli",
        "rating": 4.5,
        "count": 10,
        "maps_uri": "",
        "reviews": [],
        "fetched_at": (timezone.now() - age).isoformat(),
    }


def test_reading_prefers_the_days_answer_then_the_sites_last_good_one():
    snapshot = good()
    assert reviews.read(SLUG, PLACE, ADDRESS, snapshot) == snapshot
    fresh = {**good(), "count": 11}
    cache.set(reviews.reviews_key(SLUG, PLACE), fresh)
    assert reviews.read(SLUG, PLACE, ADDRESS, snapshot) == fresh
    cache.set(reviews.reviews_key(SLUG, PLACE), reviews.FAILED)
    assert reviews.read(SLUG, PLACE, ADDRESS, snapshot) == snapshot


def test_the_sites_last_good_answer_counts_only_for_its_place_and_for_thirty_days():
    assert reviews.read(SLUG, PLACE, ADDRESS, {}) is None
    assert reviews.read(SLUG, PLACE, ADDRESS, good(age=timedelta(days=29))) is not None
    assert reviews.read(SLUG, PLACE, ADDRESS, good(age=timedelta(days=31))) is None
    other = "ChIJOtherPlace0123456789"
    assert reviews.read(SLUG, other, ADDRESS, good()) is None
    # The same place by another of its links still counts.
    link = f"https://www.google.com/maps/place/?q=place_id:{PLACE}"
    assert reviews.read(SLUG, link, ADDRESS, good()) is not None
    assert reviews.read(SLUG, NAME_LINK, ADDRESS, good(place_ref=NAME_LINK)) is not None


def test_the_state_the_editor_shows(settings):
    assert reviews.state(SLUG, "", ADDRESS, {}) == ("empty", None)
    assert reviews.state(SLUG, PLACE, ADDRESS, {}) == ("waiting", None)
    cache.set(reviews.reviews_key(SLUG, PLACE), reviews.FAILED)
    assert reviews.state(SLUG, PLACE, ADDRESS, {}) == ("failed", None)
    snapshot = good()
    assert reviews.state(SLUG, PLACE, ADDRESS, snapshot) == ("ready", snapshot)
    settings.GOOGLE_PLACES_API_KEY = ""
    assert reviews.state(SLUG, PLACE, ADDRESS, {}) == ("unavailable", None)
    # Without the key, what was read before still shows.
    assert reviews.state(SLUG, PLACE, ADDRESS, snapshot) == ("ready", snapshot)


@respx.mock
def test_forgetting_drops_the_answer_and_the_place_found_so_the_next_load_asks_again():
    search = respx.post(SEARCH).mock(return_value=httpx.Response(200, json={"places": [{"id": PLACE}]}))
    details = respx.get(DETAILS).mock(return_value=httpx.Response(200, json=google_place()))
    reviews.load(SLUG, NAME_LINK, ADDRESS)
    reviews.forget(SLUG, NAME_LINK, ADDRESS)
    assert reviews.cached(SLUG, NAME_LINK, ADDRESS) is None
    assert reviews.known_place_id(SLUG, NAME_LINK, ADDRESS) == ""
    reviews.load(SLUG, NAME_LINK, ADDRESS)
    assert (search.call_count, details.call_count) == (2, 2)


def test_each_hub_keeps_its_own_answer():
    cache.set(reviews.reviews_key("a", PLACE), good())
    assert reviews.cached("a", PLACE, ADDRESS) is not None
    assert reviews.cached("b", PLACE, ADDRESS) is None

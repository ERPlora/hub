"""A business's own domain (HUBS-F17, PLAN-SAAS §37 point 2): what the Hub does with a host outside ``ALLOWED_HOSTS``.

The SaaS names the domain in the photo (``custom_domain``, ``PUT /internal/hubs/{id}/state``), and the Hub never asks
for it on a request. A host it does not know is what it always was, 400 from ``CommonMiddleware``, and costs no read:
since the ALB's last rule the scanners reach the Hub. A host it knows opens the business's public website, its images
and the activation's probe, and nothing else: no app, no ``/api``, no login, no ``/internal``. The page itself, with a
published site, is in ``apps/website/tests/test_custom_domain.py``.
"""

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage, storages
from django.db import OperationalError
from django.db.backends.utils import CursorWrapper

from base import custom_domains, registry
from base.models import Hub
from base.storage import hub_prefix
from base.tests.test_internal import HUB_ID, code, signed

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

DOMAIN = "www.minegocio.es"
OTHER_DOMAIN = "www.elotro.es"
UNKNOWN = "scanner.example.com"
HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
PROBE = "/.well-known/erplora-hub"
PNG = b"\x89PNG\r\n\x1a\n" + b"pixels" * 100


@pytest.fixture
def statements(monkeypatch):
    """Every statement of the test on any alias, whichever opened it: what «no read» is measured with."""
    seen: list[tuple[str, str]] = []
    original = CursorWrapper._execute_with_wrappers

    def counted(self, sql, params, many, executor):
        seen.append((self.db.alias, sql))
        return original(self, sql, params, many, executor)

    monkeypatch.setattr(CursorWrapper, "_execute_with_wrappers", counted)
    return seen


def photo(client, *, hub_id=HUB_ID, version=1, host="hubs.localhost", **body):
    """The SaaS's photo of the business ``hub_id``, as ``hubs.queries`` sends it."""
    path = f"/internal/hubs/{hub_id}/state"
    return signed(client, "put", path, {"version": version, "hub_id": str(hub_id), **body}, host=host)


@pytest.fixture
def acme(client, django_capture_on_commit_callbacks) -> Hub:
    """The business ``acme``, ready, whose last photo names :data:`DOMAIN`; this process knows it."""
    Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
    with django_capture_on_commit_callbacks(execute=True):
        answer = photo(client, custom_domain=DOMAIN)
    assert answer.status_code == 200, answer.content
    return Hub.objects.get(pk=HUB_ID)


def visit(client, path="/", host=DOMAIN, method="get", **extra):
    return getattr(client, method)(path, HTTP_HOST=host, HTTP_ACCEPT=HTML, **extra)


def the_map_was_read_just_now() -> None:
    """The next requests are inside the map's time: whatever they read is theirs."""
    custom_domains.hub_of(UNKNOWN)


# The photo: the field of the contract


class TestThePhoto:
    def test_the_row_keeps_the_domain_the_photo_names(self, client):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        assert photo(client, custom_domain=DOMAIN).json() == {"applied": True, "version": 1}
        assert Hub.objects.get(pk=HUB_ID).custom_domain == DOMAIN

    def test_it_is_kept_lowercase_and_without_its_final_dot(self, client):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        assert photo(client, custom_domain="WWW.MiNegocio.ES.").status_code == 200
        assert Hub.objects.get(pk=HUB_ID).custom_domain == DOMAIN

    def test_an_idn_domain_comes_in_its_ascii_form(self, client):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        assert photo(client, custom_domain="www.xn--peluquera-n4a.es").status_code == 200
        assert photo(client, version=2, custom_domain="www.peluquería.es").status_code == 422

    @pytest.mark.parametrize("without", [{}, {"custom_domain": None}])
    def test_a_newer_photo_that_names_none_takes_it_away(self, client, acme, without):
        assert photo(client, version=2, **without).json()["applied"] is True
        assert Hub.objects.get(pk=HUB_ID).custom_domain == ""

    def test_an_older_photo_changes_nothing(self, client, acme):
        assert photo(client, version=5, custom_domain=OTHER_DOMAIN).json()["applied"] is True
        assert photo(client, version=4, custom_domain=DOMAIN).json() == {"applied": False, "version": 5}
        assert photo(client, version=5).json() == {"applied": False, "version": 5}
        assert Hub.objects.get(pk=HUB_ID).custom_domain == OTHER_DOMAIN

    @pytest.mark.parametrize(
        "wrong",
        [
            "https://www.minegocio.es",
            "www.minegocio.es:8443",
            "www.minegocio.es/shop",
            "*.minegocio.es",
            "minegocio",
            "10.0.0.10",
            "1.2.3.4",
            "",
            " www.minegocio.es",
            42,
            ["www.minegocio.es"],
        ],
    )
    def test_what_is_no_domain_refuses_the_photo(self, client, acme, wrong):
        answer = photo(client, version=2, custom_domain=wrong)
        assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
        found = Hub.objects.get(pk=HUB_ID)
        assert found.custom_domain == DOMAIN and found.state_version == 1

    @pytest.mark.parametrize("own", ["b.erplora.com", "hubs.erplora.com", "erplora.com", "hub.erplora.internal"])
    def test_a_host_the_hub_already_answers_is_nobodys_domain(self, client, acme, settings, own):
        # It would put this business's website on another's host.
        settings.ALLOWED_HOSTS = [".erplora.com", "hub.erplora.internal"]
        answer = photo(client, version=2, host="hub.erplora.internal", custom_domain=own)
        assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
        assert Hub.objects.get(pk=HUB_ID).custom_domain == DOMAIN

    def test_the_answer_of_the_registry_never_names_it(self, client, acme):
        # The door of the photo is one way: the SaaS is who knows, and it reads nothing of it back.
        assert DOMAIN not in signed(client, "get", f"/internal/hubs/{HUB_ID}", b"").content.decode()


# A host the Hub does not know


class TestAnUnknownHost:
    @pytest.mark.parametrize("path", ["/", "/api/session/me", "/wp-login.php", PROBE, "/internal/usage"])
    def test_it_is_400_as_ever_and_reads_nothing(self, client, statements, path):
        the_map_was_read_just_now()
        statements.clear()
        assert visit(client, path, host=UNKNOWN).status_code == 400
        assert statements == []

    def test_a_session_cookie_changes_nothing(self, client, statements):
        the_map_was_read_just_now()
        # Eight characters or more: Django never looks a shorter key up.
        client.cookies["sessionid"] = "a-made-up-session-key"
        statements.clear()
        assert visit(client, "/settings", host=UNKNOWN).status_code == 400
        assert statements == []

    def test_a_flood_with_the_map_due_reads_once(self, client, statements, acme):
        custom_domains.forget()
        statements.clear()
        for number in range(20):
            assert visit(client, host=f"scanner{number}.example.com").status_code == 400
        assert len(statements) == 1

    def test_x_forwarded_host_opens_nothing(self, client, acme):
        # The ALB sends none, and a client's own is never read.
        assert visit(client, host=UNKNOWN, HTTP_X_FORWARDED_HOST=DOMAIN).status_code == 400

    def test_a_domain_nobody_has_is_no_prefix_of_one_somebody_has(self, client, acme):
        for host in ("minegocio.es", "sub.www.minegocio.es", "www.minegocio.es.evil.com"):
            assert visit(client, host=host).status_code == 400


class TestTheHostsOfTheHub:
    @pytest.mark.parametrize("host", ["a.localhost:8000", "hubs.localhost:8000", "localhost:8000"])
    def test_they_never_ask_the_map(self, client, monkeypatch, host):
        def no(*args):
            raise AssertionError("a host of the Hub asked for the domains")

        custom_domains.forget()
        monkeypatch.setattr(registry, "custom_domains", no)
        assert visit(client, "/readyz", host=host).status_code in (200, 503)

    def test_a_hubs_own_host_is_no_door_of_the_domain(self, client, acme):
        # acme's own address keeps the whole app: nothing changes there.
        response = visit(client, "/settings", host="acme.localhost:8000")
        assert response.status_code == 200 and "hub-jump" in response.content.decode()


# A host the Hub knows: what is closed


CLOSED = [
    "/settings",
    "/login",
    "/demo/items",
    "/admin/",
    "/admin/login/",
    "/auth/login",
    "/auth/logout",
    "/auth/pin",
    "/auth/badge",
    "/auth/callback",
    "/readyz",
    "/csp-report/",
    "/favicon.ico",
    "/robots.txt",
    "/p/catalog/food/cafe.webp",
    "/.well-known/acme-challenge/x",
    "/.well-known/erplora-hub/",
]
CLOSED_API = [
    "/api/session/me",
    "/api/live",
    "/api/error-report",
    "/api/website/site",
    "/api/website/public/site",
    "/api/website/public/catalog",
    "/api/website/public/reviews",
    "/api/openapi.json",
]


class TestWhatIsClosedOnTheDomain:
    @pytest.mark.parametrize("path", CLOSED + CLOSED_API)
    def test_a_read_of_it_is_404_and_reads_nothing(self, client, acme, statements, path):
        the_map_was_read_just_now()
        statements.clear()
        response = visit(client, path)
        assert response.status_code == 404
        assert not response.cookies
        assert statements == []

    @pytest.mark.parametrize("path", ["/auth/callback", "/auth/logout", "/auth/pin", "/api/session/me", "/api/live", "/settings"])
    def test_a_write_to_it_is_404(self, client, acme, path):
        assert visit(client, path, method="post").status_code == 404

    @pytest.mark.parametrize("path", CLOSED_API)
    def test_the_api_answers_its_own_envelope(self, client, acme, path):
        response = visit(client, path, HTTP_ACCEPT_LANGUAGE="es")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_with_debug_it_is_still_404_and_not_the_400_of_the_technical_page(self, client, acme, settings):
        # Django's technical 404 asks get_host(), which a host outside ALLOWED_HOSTS answers with a 400.
        settings.DEBUG = True
        assert visit(client, "/settings").status_code == 404
        assert visit(client).status_code == 404

    def test_the_login_never_opens_a_session_nor_leaves_its_state(self, client, acme):
        response = visit(client, "/auth/login?next=/settings")
        assert response.status_code == 404 and not response.cookies

    def test_a_good_signature_does_not_open_internal(self, client, acme):
        # The door answers on any host of the Hub; a business's domain is none of them.
        answer = photo(client, version=2, host=DOMAIN)
        assert answer.status_code == 404
        found = Hub.objects.get(pk=HUB_ID)
        assert found.custom_domain == DOMAIN and found.state_version == 1
        assert signed(client, "get", "/internal/usage?day=2026-11-01", b"", host=DOMAIN).status_code == 404

    def test_a_session_of_the_business_opens_nothing_more(self, client, acme, make_user):
        client.force_login(make_user("ana", host="acme"))
        for path in ("/settings", "/api/session/me", "/auth/login"):
            assert visit(client, path).status_code == 404

    def test_a_write_to_the_home_is_not_allowed(self, client, acme):
        assert visit(client, method="post").status_code == 405
        assert visit(client, PROBE, method="delete").status_code == 405

    def test_health_is_still_answered_before_any_host(self, client, acme):
        # The ALB's probe of the task, the one thing the first middleware answers on every host.
        assert visit(client, "/healthz").json() == {"status": "ok"}


# A host the Hub knows: when it stops serving


class TestWhenItStopsServing:
    def test_a_business_without_a_website_serves_nothing(self, client, acme):
        assert visit(client).status_code == 404

    def test_a_domain_given_up_stops_at_once_even_before_the_map_is_read_again(self, client, acme, hub_files, every_app_on):
        every_app_on("acme")
        hub_files.save(f"{hub_prefix(acme.id)}/website/img/3f2a9c.png", ContentFile(PNG))
        image = f"/p/media/{acme.id.hex}/website/img/3f2a9c.png"
        assert visit(client, image).status_code == 200
        assert photo(client, version=2).status_code == 200  # The commit is the test's: the map stays as it was.
        assert custom_domains.hub_of(DOMAIN) == acme.id
        assert visit(client, image).status_code == 404

    def test_a_domain_given_up_is_unknown_once_the_map_is_read_again(self, client, acme):
        the_map_was_read_just_now()
        assert photo(client, version=2).status_code == 200
        custom_domains.forget()
        assert visit(client).status_code == 400
        assert visit(client, PROBE).status_code == 400

    @pytest.mark.parametrize("status", [Hub.Status.CANCELLED, Hub.Status.ARCHIVING, Hub.Status.DROPPING, Hub.Status.PURGED])
    def test_a_business_that_left_serves_nothing(self, client, acme, status):
        the_map_was_read_just_now()
        Hub.objects.filter(pk=acme.pk).update(status=status)
        assert visit(client).status_code == 404  # The map, not read again yet.
        custom_domains.forget()
        assert visit(client).status_code == 400
        assert visit(client, PROBE).status_code == 400

    def test_a_business_suspended_says_nothing_of_its_invoice_to_a_visitor(self, client, acme):
        Hub.objects.filter(pk=acme.pk).update(state={"status": "suspended"})
        response = visit(client)
        assert response.status_code == 404
        assert "invoice" not in response.content.decode().lower()

    @pytest.mark.parametrize("status", [Hub.Status.CREATING, Hub.Status.MIGRATING, Hub.Status.SEEDING])
    def test_a_business_being_prepared_says_come_back(self, client, acme, status):
        Hub.objects.filter(pk=acme.pk).update(status=status)
        response = visit(client)
        assert response.status_code == 503 and response["Retry-After"]

    def test_a_business_moving_to_another_cluster_says_come_back(self, client, acme):
        from control.models import Cluster

        cluster = Cluster.objects.create(name="other", host="other.internal")
        Hub.objects.filter(pk=acme.pk).update(moving_to=cluster)
        response = visit(client)
        assert response.status_code == 503 and response["Retry-After"]

    def test_a_database_that_cannot_be_reached_is_503(self, client, acme, monkeypatch):
        def down(request):
            raise OperationalError("the failover")

        monkeypatch.setattr("base.middleware.website_enabled", down)
        response = visit(client)
        assert response.status_code == 503 and response["Retry-After"]
        assert response.json()["error"]["code"] == registry.HUB_UNAVAILABLE


# The activation's probe


class TestTheProbe:
    def test_it_gives_the_hubs_id_and_nothing_else(self, client, acme, statements):
        the_map_was_read_just_now()
        statements.clear()
        response = client.get(PROBE, HTTP_HOST=DOMAIN)
        assert response.status_code == 200
        assert response.json() == {"hub_id": str(acme.id)}
        assert not response.cookies
        assert "no-store" in response["Cache-Control"]
        assert statements == []

    def test_it_answers_before_the_site_is_published(self, client, acme):
        assert visit(client).status_code == 404
        assert visit(client, PROBE).json() == {"hub_id": str(acme.id)}

    def test_each_domain_gives_the_id_of_its_own_business(self, client, acme, django_capture_on_commit_callbacks):
        other_id = "0199c4b0-0000-7000-8000-000000000002"
        Hub.objects.create(id=other_id, slug="other", status="ready")
        with django_capture_on_commit_callbacks(execute=True):
            photo(client, hub_id=other_id, custom_domain=OTHER_DOMAIN)
        assert visit(client, PROBE, host=OTHER_DOMAIN).json() == {"hub_id": other_id}
        assert visit(client, PROBE).json() == {"hub_id": str(acme.id)}

    def test_it_is_only_on_the_domain(self, client, acme):
        # On the business's own address, that path is any other of the SPA's.
        response = visit(client, PROBE, host="acme.localhost:8000")
        assert str(acme.id) not in response.content.decode()


# The images of the website


@pytest.fixture
def hub_files(settings):
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": f"{InMemoryStorage.__module__}.InMemoryStorage"}}
    return storages["hub_files"]


class TestTheImages:
    def test_a_public_image_of_the_business_is_served(self, client, acme, hub_files, every_app_on):
        every_app_on("acme")
        hub_files.save(f"{hub_prefix(acme.id)}/website/img/3f2a9c.png", ContentFile(PNG))
        response = visit(client, f"/p/media/{acme.id.hex}/website/img/3f2a9c.png")
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PNG
        assert response["Cache-Control"] == "public, max-age=31536000, immutable"
        assert not response.cookies

    def test_another_business_never_serves_its_images_here(self, client, acme, hub_files, statements):
        other = Hub.objects.get(slug="a")
        hub_files.save(f"{hub_prefix(other.id)}/website/img/3f2a9c.png", ContentFile(PNG))
        the_map_was_read_just_now()
        statements.clear()
        assert visit(client, f"/p/media/{other.id.hex}/website/img/3f2a9c.png").status_code == 404
        assert statements == []

    def test_a_members_file_stays_theirs_even_with_their_session(self, client, acme, hub_files, make_user):
        hub_files.save(f"{hub_prefix(acme.id)}/avatars/ana.png", ContentFile(PNG))
        client.force_login(make_user("ana", host="acme"))
        assert visit(client, f"/p/media/{acme.id.hex}/avatars/ana.png").status_code == 404

    def test_a_business_that_left_serves_no_image(self, client, acme, hub_files, every_app_on):
        every_app_on("acme")
        hub_files.save(f"{hub_prefix(acme.id)}/website/img/3f2a9c.png", ContentFile(PNG))
        the_map_was_read_just_now()
        Hub.objects.filter(pk=acme.pk).update(status=Hub.Status.CANCELLED)
        assert visit(client, f"/p/media/{acme.id.hex}/website/img/3f2a9c.png").status_code == 404


# The map


class TestTheMap:
    def test_the_host_is_read_as_a_browser_writes_it(self, client, acme):
        for host in ("WWW.MINEGOCIO.ES", "www.minegocio.es:443", "www.minegocio.es."):
            assert visit(client, PROBE, host=host).json() == {"hub_id": str(acme.id)}

    def test_a_domain_two_businesses_name_is_nobodys(self, client, acme, caplog, django_capture_on_commit_callbacks):
        # Its move between businesses: two photos in any order, with no order between their versions. The Hub never
        # chooses a website for it, and neither photo is refused.
        other_id = "0199c4b0-0000-7000-8000-000000000002"
        Hub.objects.create(id=other_id, slug="other", status="ready")
        with django_capture_on_commit_callbacks(execute=True):
            assert photo(client, hub_id=other_id, custom_domain=DOMAIN).json()["applied"] is True
        assert custom_domains.hub_of(DOMAIN) is None
        assert visit(client, PROBE).status_code == 400
        assert "base.custom_domain_taken" in caplog.text
        with django_capture_on_commit_callbacks(execute=True):
            assert photo(client, version=2).json()["applied"] is True
        assert custom_domains.hub_of(DOMAIN) is not None
        assert visit(client, PROBE).json() == {"hub_id": other_id}

    def test_it_is_read_again_only_when_its_time_is_up(self, client, acme, monkeypatch, statements):
        now = [1000.0]
        monkeypatch.setattr(custom_domains, "monotonic", lambda: now[0])
        custom_domains.forget()
        assert custom_domains.hub_of(DOMAIN) == acme.id
        statements.clear()
        now[0] += custom_domains.REFRESH_SECONDS - 1
        assert custom_domains.hub_of(DOMAIN) == acme.id
        assert statements == []
        now[0] += 1
        assert custom_domains.hub_of(DOMAIN) == acme.id
        assert len(statements) == 1

    def test_a_new_domain_reaches_another_process_when_its_time_is_up(self, client, acme, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(custom_domains, "monotonic", lambda: now[0])
        custom_domains.forget()
        custom_domains.hub_of(DOMAIN)
        # Written by another process: nothing here forgets.
        Hub.objects.filter(pk=acme.pk).update(custom_domain=OTHER_DOMAIN)
        assert custom_domains.hub_of(OTHER_DOMAIN) is None
        now[0] += custom_domains.REFRESH_SECONDS
        assert custom_domains.hub_of(OTHER_DOMAIN) == acme.id
        assert custom_domains.hub_of(DOMAIN) is None

    def test_a_photo_that_changes_the_domain_is_known_in_this_process_at_once(
        self, client, acme, django_capture_on_commit_callbacks
    ):
        the_map_was_read_just_now()
        with django_capture_on_commit_callbacks(execute=True):
            photo(client, version=2, custom_domain=OTHER_DOMAIN)
        assert custom_domains.hub_of(OTHER_DOMAIN) == acme.id
        assert custom_domains.hub_of(DOMAIN) is None

    def test_a_photo_that_does_not_change_it_keeps_the_map(self, client, acme, django_capture_on_commit_callbacks, statements):
        the_map_was_read_just_now()
        with django_capture_on_commit_callbacks(execute=True):
            photo(client, version=2, custom_domain=DOMAIN)
        statements.clear()
        assert custom_domains.hub_of(DOMAIN) == acme.id
        assert statements == []

    def test_a_failed_read_keeps_what_was_known_and_says_so(self, client, acme, monkeypatch, caplog):
        now = [1000.0]
        monkeypatch.setattr(custom_domains, "monotonic", lambda: now[0])
        custom_domains.forget()
        custom_domains.hub_of(DOMAIN)
        calls = []

        def down():
            calls.append(1)
            raise OperationalError("the failover")

        monkeypatch.setattr(registry, "custom_domains", down)
        now[0] += custom_domains.REFRESH_SECONDS
        assert custom_domains.hub_of(DOMAIN) == acme.id
        assert "base.custom_domains_unread" in caplog.text
        # Not on every request while it lasts, and soon after it.
        assert custom_domains.hub_of(DOMAIN) == acme.id
        assert len(calls) == 1
        now[0] += custom_domains.RETRY_SECONDS
        custom_domains.hub_of(DOMAIN)
        assert len(calls) == 2


def test_the_door_of_the_domain_is_the_gate_right_before_the_host_is_refused(settings):
    # Before CommonMiddleware, whose get_host() is the 400; after the session's and the language's, which read nothing.
    order = settings.MIDDLEWARE
    door = order.index("base.middleware.CustomDomainMiddleware")
    assert order[door + 1] == "django.middleware.common.CommonMiddleware"
    assert order[door - 1] == "django.middleware.locale.LocaleMiddleware"


"""``/healthz``: the process is up. It never touches the database.

The load balancer probes each task by its IP, a Host that ``ALLOWED_HOSTS`` rejects, so the
answer comes from a middleware placed before anything that validates the Host
(``CommonMiddleware``, ``CsrfViewMiddleware``…).
"""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin

HEALTHZ_PATH = "/healthz"


def healthz(request: HttpRequest) -> HttpResponse:
    return JsonResponse({"status": "ok"})


class HealthCheckMiddleware(MiddlewareMixin):
    """Answer ``/healthz`` on any Host, before the rest of the middleware runs."""

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        if request.path == HEALTHZ_PATH:
            return healthz(request)
        return None

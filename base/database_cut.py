"""The Hub's side of a cut of the database (``live.database_cut``).

``live`` decides what a cut is, what may run again and who waits; the Hub answers it. :func:`server_error` is the
``handler500``: a cut that escaped a view or a middleware (the host's business read on control, the session) is 503 with
``Retry-After`` instead of a 500, marked for ``live.database_cut.DatabaseCutMiddleware``, which waits and repeats the
request while it may. Past the limit, or when it may not repeat, that is what the person gets: the envelope for the API
and for any call that does not ask for a page, and for a browser ``base/database_cut.html``, a gate page that refreshes
itself, saying ERPlora will be back in a moment. It is rendered without the request: no context processor runs, since
they read the database that is gone.
"""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.views import defaults
from live.database_cut import DatabaseCut, current_cut, marked

from base.middleware import wants_envelope

#: The page of a cut past the limit of its wait: a gate page (base/gate.html) that refreshes itself.
DATABASE_CUT_TEMPLATE = "base/database_cut.html"


def server_error(request: HttpRequest) -> HttpResponse:
    """``handler500``: a cut of the database is 503 for a moment, anything else Django's own 500."""
    cut = current_cut(request)
    if cut is None:
        return defaults.server_error(request)
    return marked(come_back(request, cut), cut)


def come_back(request: HttpRequest, cut: DatabaseCut) -> HttpResponse:
    """What a person reads of ``cut``: its envelope, or the page that refreshes itself until ERPlora is back."""
    if wants_envelope(request):
        return JsonResponse(cut.envelope(), status=cut.status)
    return HttpResponse(render_to_string(DATABASE_CUT_TEMPLATE, {"message": cut.message}), status=cut.status)

from django.http import HttpResponse
from django.template.loader import render_to_string


class ErrorPageMiddleware:
    """Render custom error pages for HTTP error responses that Django
    doesn't handle with templates by default (e.g. 405)."""

    TEMPLATE_MAP = {
        405: '405.html',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code in self.TEMPLATE_MAP:
            # Skip for API/HTMX requests — they expect JSON or fragments
            if request.path.startswith('/api/') or request.headers.get('HX-Request'):
                return response

            template = self.TEMPLATE_MAP[response.status_code]
            html = render_to_string(template, request=request)
            return HttpResponse(html, status=response.status_code)

        return response

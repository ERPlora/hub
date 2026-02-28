"""
Tests for HTMX utilities - decorator and helper functions.

Tests the @htmx_view decorator and related utilities that enable
SPA-like navigation with HTMX.
"""
import pytest
from django.test import RequestFactory
from django.http import HttpResponse
from unittest.mock import patch, MagicMock

from apps.core.htmx import (
    htmx_view,
    is_htmx_request,
    htmx_redirect,
    htmx_refresh,
)


class TestHtmxViewDecorator:
    """Tests for @htmx_view decorator"""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_full_page_without_htmx_header(self):
        """Regular request renders full page template"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_view(request):
            return {'data': 'test'}

        request = self.factory.get('/test/')

        with patch('apps.core.htmx.render') as mock_render:
            mock_render.return_value = HttpResponse('full page')
            response = my_view(request)

            mock_render.assert_called_once_with(
                request, 'pages/full.html', {'data': 'test', 'content_template': 'partials/content.html'}
            )

    def test_partial_with_htmx_header(self):
        """HTMX request renders partial template"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_view(request):
            return {'data': 'test'}

        request = self.factory.get('/test/', HTTP_HX_REQUEST='true')

        with patch('apps.core.htmx.render') as mock_render:
            mock_render.return_value = HttpResponse('partial')
            response = my_view(request)

            mock_render.assert_called_once_with(
                request, 'partials/content.html', {'data': 'test'}
            )

    def test_partial_with_query_param(self):
        """?partial=true renders partial template (for testing)"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_view(request):
            return {'data': 'test'}

        request = self.factory.get('/test/?partial=true')

        with patch('apps.core.htmx.render') as mock_render:
            mock_render.return_value = HttpResponse('partial')
            response = my_view(request)

            mock_render.assert_called_once_with(
                request, 'partials/content.html', {'data': 'test'}
            )

    def test_query_param_false_renders_full(self):
        """?partial=false still renders full template"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_view(request):
            return {'data': 'test'}

        request = self.factory.get('/test/?partial=false')

        with patch('apps.core.htmx.render') as mock_render:
            mock_render.return_value = HttpResponse('full page')
            response = my_view(request)

            mock_render.assert_called_once_with(
                request, 'pages/full.html', {'data': 'test', 'content_template': 'partials/content.html'}
            )

    def test_htmx_takes_precedence_over_query_param(self):
        """HTMX header works regardless of query param"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_view(request):
            return {'data': 'test'}

        # HTMX request with partial=false should still render partial
        request = self.factory.get('/test/?partial=false', HTTP_HX_REQUEST='true')

        with patch('apps.core.htmx.render') as mock_render:
            mock_render.return_value = HttpResponse('partial')
            response = my_view(request)

            mock_render.assert_called_once_with(
                request, 'partials/content.html', {'data': 'test'}
            )

    def test_view_returns_httpresponse_directly(self):
        """If view returns HttpResponse, decorator passes it through"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_view(request):
            return HttpResponse('direct response', status=201)

        request = self.factory.get('/test/')

        response = my_view(request)
        assert response.status_code == 201
        assert response.content == b'direct response'

    def test_view_returns_empty_context(self):
        """View returning None or empty uses empty context"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_view(request):
            return None

        request = self.factory.get('/test/')

        with patch('apps.core.htmx.render') as mock_render:
            mock_render.return_value = HttpResponse('')
            response = my_view(request)

            mock_render.assert_called_once_with(
                request, 'pages/full.html', {'content_template': 'partials/content.html'}
            )

    def test_preserves_function_metadata(self):
        """Decorator preserves original function name and docstring"""

        @htmx_view('pages/full.html', 'partials/content.html')
        def my_documented_view(request):
            """This is my docstring"""
            return {}

        assert my_documented_view.__name__ == 'my_documented_view'
        assert my_documented_view.__doc__ == 'This is my docstring'


class TestIsHtmxRequest:
    """Tests for is_htmx_request helper"""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_returns_true_for_htmx_request(self):
        """Returns True when request has HX-Request header"""
        request = self.factory.get('/test/', HTTP_HX_REQUEST='true')

        assert is_htmx_request(request) is True

    def test_returns_true_for_partial_param(self):
        """Returns True when ?partial=true is present"""
        request = self.factory.get('/test/?partial=true')

        assert is_htmx_request(request) is True

    def test_returns_false_for_regular_request(self):
        """Returns False for regular request"""
        request = self.factory.get('/test/')

        assert is_htmx_request(request) is False

    def test_returns_false_for_partial_false(self):
        """Returns False when ?partial=false"""
        request = self.factory.get('/test/?partial=false')

        assert is_htmx_request(request) is False


class TestHtmxRedirect:
    """Tests for htmx_redirect helper"""

    def test_sets_hx_redirect_header(self):
        """Response includes HX-Redirect header"""
        response = htmx_redirect('/dashboard/')

        assert response['HX-Redirect'] == '/dashboard/'
        assert response.status_code == 200

    def test_accepts_full_url(self):
        """Works with full URLs"""
        response = htmx_redirect('https://example.com/path/')

        assert response['HX-Redirect'] == 'https://example.com/path/'


class TestHtmxRefresh:
    """Tests for htmx_refresh helper"""

    def test_sets_hx_refresh_header(self):
        """Response includes HX-Refresh header"""
        response = htmx_refresh()

        assert response['HX-Refresh'] == 'true'
        assert response.status_code == 200

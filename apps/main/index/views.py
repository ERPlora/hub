"""
Main Index Views - Dashboard home
"""
from django.shortcuts import redirect
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required


@login_required
@htmx_view('main/index/pages/index.html', 'main/index/partials/content.html')
def index(request):
    """Dashboard home page"""
    return {
        'current_section': 'dashboard',
        'page_title': 'Dashboard',
    }

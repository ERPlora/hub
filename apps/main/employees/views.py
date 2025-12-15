"""
Main Employees Views
"""
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.accounts.models import LocalUser


@login_required
@htmx_view('main/employees/pages/index.html', 'main/employees/partials/content.html')
def index(request):
    """Employees management page"""
    local_users = LocalUser.objects.filter(is_active=True).order_by('name')

    return {
        'current_section': 'employees',
        'page_title': 'Employees',
        'local_users': local_users,
    }

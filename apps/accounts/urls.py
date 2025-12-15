"""
Accounts URLs

This app only provides models and middleware.
All URL routes are now in their proper apps:
- Authentication: apps.auth.login
- Employees: apps.main.employees
- API: apps.accounts.api (registered in config/urls.py)
"""
from django.urls import path

app_name = 'accounts'

# No URL patterns - all routes migrated to proper apps
urlpatterns = []

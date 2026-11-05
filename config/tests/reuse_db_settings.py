"""The settings of the runs of ``test_reuse_db.py``: of the business apps, only the one with the factory data.

Those runs make their database twice, and the other apps' migrations would be most of what that takes.
"""

from config.settings_pytest import *  # noqa: F403
from config.settings_pytest import INSTALLED_APPS

INSTALLED_APPS = [app for app in INSTALLED_APPS if not app.startswith("apps.") or app == "apps.tax"]

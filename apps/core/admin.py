from django.contrib import admin

# Models have been moved to their respective apps:
# - LocalUser -> apps.accounts.models
# - HubConfig, StoreConfig -> apps.configuration.models
# - Module -> apps.modules.models
# - TokenCache, SyncQueue -> apps.sync.models
#
# Admin registration is now in each app's admin.py file

"""
Core app models.

This module previously contained the Module model for tracking installed modules,
but that has been removed. Module metadata is now loaded entirely from the filesystem:

- Active modules: modules/{module_id}/ (no prefix)
- Inactive modules: modules/_{module_id}/ (underscore prefix)
- Hidden modules: modules/.{module_id}/ (dot prefix)

All module metadata comes from module.py files in each module directory.

Other models have been refactored to their respective apps:
- LocalUser → apps.accounts.models
- HubConfig, StoreConfig → apps.configuration.models
- TokenCache, SyncQueue → apps.sync.models
"""

# No models in this file - all module data is filesystem-based

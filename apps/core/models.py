"""
Core app models.

All models have been refactored and moved to their respective apps:

- LocalUser → apps.accounts.models
- HubConfig, StoreConfig → apps.configuration.models
- Plugin → apps.plugins.models
- TokenCache, SyncQueue → apps.sync.models

The core app now serves as a utility app for:
- Context processors (context_processors.py)
- Update management (update_manager.py)
- FRP client (frp_client.py)
- Startup tasks (startup.py)
- WebSocket client (websocket_client.py)
- Shared services (services/)
- Template tags (templatetags/)
"""

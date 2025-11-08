"""
Hub startup tasks.

Runs initialization tasks when the Hub starts, including:
- Version checking
- System health checks
- Plugin loading
- WebSocket connection
"""

import logging
from threading import Thread
from .update_manager import update_manager

logger = logging.getLogger(__name__)


def check_for_updates_async():
    """
    Check for updates in a background thread to avoid blocking startup.

    This runs asynchronously so the Hub can start immediately while
    the version check happens in the background.
    """
    try:
        logger.info("Checking for updates in background...")
        result = update_manager.check_for_updates()

        if result.get('error'):
            logger.warning(f"Update check failed: {result['error']}")
            return

        if result.get('update_available'):
            logger.info(
                f"🔔 Update available: {result['current_version']} -> {result['latest_version']} "
                f"({result['update_type']})"
            )

            # TODO: Show notification in UI
            # This will be handled by the frontend once WebSocket is connected

        else:
            logger.info(f"✅ Running latest version: {result['current_version']}")

    except Exception as e:
        logger.exception(f"Error in background update check: {e}")


def run_startup_tasks():
    """
    Execute all startup tasks.

    Called when the Hub Django app is ready (apps.py ready() method).
    """
    logger.info("Running Hub startup tasks...")

    # Check for updates in background thread
    update_thread = Thread(target=check_for_updates_async, daemon=True)
    update_thread.start()

    # TODO: Add other startup tasks:
    # - Check WebSocket connection to Cloud
    # - Verify database integrity
    # - Load installed plugins
    # - Initialize hardware services

    logger.info("Startup tasks initiated")

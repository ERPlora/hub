import locale
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def schedule_server_restart(delay=2):
    """Schedule a server restart after sending the current response.

    In Docker: os._exit(0) terminates the process. Docker's restart policy
    (restart: unless-stopped) brings the container back with all new modules
    loaded fresh from settings.

    In local dev: touches wsgi.py to trigger runserver's autoreload.

    Args:
        delay: Seconds to wait before restarting (lets the response be sent).
    """
    from config.paths import is_docker_environment

    def _restart():
        import time
        time.sleep(delay)
        if is_docker_environment():
            logger.info("Exiting process for Docker restart")
            os._exit(0)
        else:
            from django.conf import settings
            wsgi_file = Path(settings.BASE_DIR) / 'config' / 'wsgi.py'
            if wsgi_file.exists():
                wsgi_file.touch()
                logger.info("Touched wsgi.py to trigger autoreload")

    threading.Thread(target=_restart, daemon=True).start()
    logger.info("Server restart scheduled in %ds", delay)


def detect_os_language():
    """
    Detect the operating system's language.
    Returns 'en' or 'es' based on OS locale.
    """
    try:
        # Try to get the system locale
        system_locale, _ = locale.getdefaultlocale()

        if system_locale:
            # Extract language code (first 2 characters)
            lang_code = system_locale[:2].lower()

            # Map to supported languages
            if lang_code == 'es':
                return 'es'
            else:
                return 'en'  # Default to English

        # Fallback: try environment variables
        env_lang = os.environ.get('LANG', '').lower()
        if 'es' in env_lang:
            return 'es'

        return 'en'  # Default

    except Exception:
        return 'en'  # Default on error

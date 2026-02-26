import locale
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def schedule_server_restart(delay=2):
    """Schedule a graceful server reload after sending the current response.

    In Docker/gunicorn: sends SIGHUP to the gunicorn master process for
    graceful worker reload (zero downtime). Reads PID from /run/gunicorn.pid.

    In local dev: touches wsgi.py to trigger runserver's autoreload.

    Args:
        delay: Seconds to wait before restarting (lets the response be sent).
    """
    import signal

    def _restart():
        import time
        time.sleep(delay)

        # Try gunicorn graceful reload via SIGHUP
        pidfile = Path('/run/gunicorn.pid')
        if pidfile.exists():
            try:
                master_pid = int(pidfile.read_text().strip())
                os.kill(master_pid, signal.SIGHUP)
                logger.info("Sent SIGHUP to gunicorn master (pid=%d)", master_pid)
                return
            except (ValueError, ProcessLookupError, PermissionError) as e:
                logger.warning("SIGHUP failed: %s, falling back", e)

        # Fallback: Docker without pidfile → os._exit
        from config.paths import is_docker_environment
        if is_docker_environment():
            logger.info("No gunicorn pidfile, exiting for Docker restart")
            os._exit(0)
        else:
            # Local dev: touch wsgi.py for runserver autoreload
            from django.conf import settings
            wsgi_file = Path(settings.BASE_DIR) / 'config' / 'wsgi.py'
            if wsgi_file.exists():
                wsgi_file.touch()
                logger.info("Touched wsgi.py to trigger autoreload")

    threading.Thread(target=_restart, daemon=True).start()
    logger.info("Server reload scheduled in %ds", delay)


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

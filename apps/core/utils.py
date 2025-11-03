import locale
import os


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

#!/usr/bin/env python3
"""
CPOS Hub - Main entry point for PyInstaller builds
This file wraps Django's manage.py for PyInstaller packaging
"""
import os
import sys
from pathlib import Path

# Add the project directory to the Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def main():
    """Run the Django management command"""
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Run the server by default (for PyInstaller builds)
    # In development, use manage.py directly
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        execute_from_command_line(['manage.py', 'runserver', '0.0.0.0:8001', '--noreload'])
    else:
        # Running in development
        execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

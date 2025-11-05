"""
CPOS Hub - Point of Sale Desktop Application
"""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("cpos-hub")
except PackageNotFoundError:
    # Package not installed, use fallback
    __version__ = "0.0.0.dev"

__all__ = ["__version__"]

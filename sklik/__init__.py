"""Sklik DRAK CLI package."""
import warnings

# Silence urllib3's LibreSSL/OpenSSL warning BEFORE requests/urllib3 is imported
# by any submodule; must run first so stdout JSON is never corrupted.
warnings.filterwarnings("ignore", message=r".*OpenSSL.*")

__version__ = "1.9.0"

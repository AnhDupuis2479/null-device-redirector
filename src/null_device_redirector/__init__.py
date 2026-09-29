"""Null Device Redirector package.

Re-exports the public API from :mod:`null_device_redirector.core`.
"""

from null_device_redirector.core import null_redirect, NullRedirect

__all__ = ["null_redirect", "NullRedirect"]

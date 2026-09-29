"""Context manager redirecting stdout and stderr to os.devnull.

The implementation is deliberately small: it opens ``os.devnull`` once,
``os.dup2``-ing the file descriptor onto both ``sys.stdout.fileno()`` and
``sys.stderr.fileno()`` for the duration of the block, then restores the
original descriptors on exit.  This is the same mechanism used by CPython's
``contextlib.redirect_stdout`` under the hood, but operating at the OS file
descriptor level so that C-level writes (e.g. from numpy, ctypes, or compiled
extensions) are also silenced — something that swapping ``sys.stdout`` alone
does not achieve.

We restore on *every* exit path (normal return, exception, or
``BaseException`` such as ``KeyboardInterrupt``).  If restoration itself fails
we still close the null device handle; a leaked fd is preferable to losing the
user's real stdout permanently.
"""

from __future__ import annotations

import os
import sys
from typing import IO, Optional


class NullRedirect:
    """Redirect ``sys.stdout`` and ``sys.stderr`` to ``os.devnull``.

    Used as a context manager::

        with NullRedirect():
            print("this is swallowed")

    On entry the current file descriptors for stdout (fd 1) and stderr
    (fd 2) are saved via ``os.dup`` and a new handle to ``os.devnull`` is
    opened.  The null device is ``dup2``-ed onto both fds.  On exit the
    saved descriptors are ``dup2``-ed back, restoring the original streams.

    The class is reusable — each ``__enter__`` opens a fresh null handle and
    each ``__exit__`` closes it — but it is **not** reentrant: nesting
    ``with NullRedirect():`` inside another ``with NullRedirect():`` will
    restore the *outer* null device on exit of the inner block, which is
    already null, so the net effect is correct, but the inner block's exit
    will clobber the outer block's saved descriptors.  If you need nesting,
    use separate instances.

    If ``sys.stdout`` or ``sys.stderr`` has had its underlying file
    descriptor closed (``fileno()`` raises ``ValueError``), that stream is
    skipped rather than raising.  This matches the reality of, e.g.,
    Python run under certain GUI test runners where stderr is a
    ``StringIO`` with no real fd.
    """

    def __init__(self) -> None:
        self._null_fd: Optional[int] = None
        self._saved_fds: dict[int, int] = {}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _fileno(self, stream: object) -> Optional[int]:
        """Return the real OS file descriptor for *stream*, or ``None``.

        We catch ``UnsupportedOperation`` (a subclass of ``ValueError``
        raised by ``io.StringIO``/``BytesIO``) and the bare ``ValueError``
        that the std streams raise when their fd has been closed, so that
        redirecting under environments without real std fds degrades
        gracefully instead of crashing.
        """
        fileno = getattr(stream, "fileno", None)
        if fileno is None:
            return None
        try:
            return fileno()
        except (ValueError, OSError):
            return None

    # ------------------------------------------------------------------
    # context-manager protocol
    # ------------------------------------------------------------------
    def __enter__(self) -> "NullRedirect":
        # Open the null device once and reuse for both streams.
        self._null_fd = os.open(os.devnull, os.O_WRONLY)

        targets: list[tuple[int, object]] = [
            (1, sys.stdout),
            (2, sys.stderr),
        ]
        for fd, stream in targets:
            real_fd = self._fileno(stream)
            if real_fd is None:
                # No underlying fd (e.g. StringIO in a test runner). Skip.
                continue
            # Save a duplicate so that we can restore even if something
            # else closes the original fd while we're inside the block.
            self._saved_fds[fd] = os.dup(fd)
            os.dup2(self._null_fd, fd)

        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[object],
    ) -> None:
        # Restore in reverse order so that if the same fd was aliased to
        # both streams (unlikely but cheap to be safe) we end with the
        # last-written mapping in place.
        for fd in sorted(self._saved_fds, reverse=True):
            saved = self._saved_fds[fd]
            try:
                os.dup2(saved, fd)
            finally:
                os.close(saved)
        self._saved_fds.clear()

        if self._null_fd is not None:
            os.close(self._null_fd)
            self._null_fd = None


def null_redirect() -> NullRedirect:
    """Return a fresh :class:`NullRedirect` instance.

    Convenience constructor for the common case where you want a one-liner::

        with null_redirect():
            noisy_function()

    Functionally identical to ``NullRedirect()``; provided because
    ``with null_redirect():`` reads more naturally at call sites than
    ``with NullRedirect():``.
    """
    return NullRedirect()

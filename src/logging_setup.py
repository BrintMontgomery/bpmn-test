"""Shared logging configuration that keeps default CLI stdout/stderr text
byte-identical to the pre-logging print()-based output.

Handlers write through a proxy that resolves ``sys.stdout`` / ``sys.stderr``
at *emit* time rather than at handler-construction time. This matters
because this repository's test suite uses
``contextlib.redirect_stdout``/``redirect_stderr`` around direct calls into
library functions (not just CLI ``main()``), and this module's handlers are
constructed once, the first time any module imports it -- typically well
before any test's ``redirect_stdout`` block runs. Binding the stream
reference eagerly would send output to the *original* stdout object and
silently break every redirect-based assertion in the suite.
"""

from __future__ import annotations

import logging
import sys


class _StreamProxy:
    """Forward writes to whatever ``sys.<stream_name>`` is at call time."""

    def __init__(self, stream_name: str) -> None:
        self._stream_name = stream_name

    def write(self, message: str) -> int:
        return getattr(sys, self._stream_name).write(message)

    def flush(self) -> None:
        getattr(sys, self._stream_name).flush()


_CONFIGURED = False


def configure() -> None:
    """Attach plain-text stdout/stderr handlers to the root logger, once.

    Idempotent and safe to call from every module that logs -- import order
    doesn't matter, and repeated calls are no-ops after the first.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    formatter = logging.Formatter("%(message)s")

    stdout_handler = logging.StreamHandler(_StreamProxy("stdout"))
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)

    stderr_handler = logging.StreamHandler(_StreamProxy("stderr"))
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)

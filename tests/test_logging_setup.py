from __future__ import annotations

import io
import sys
import unittest

from logging_setup import _StreamProxy


class StreamProxyTests(unittest.TestCase):
    """Regression coverage for the redirect-after-construction ordering that
    motivated this proxy: handlers are built once at import time, well before
    any test's contextlib.redirect_stdout block runs.
    """

    def test_writes_go_to_whatever_sys_stdout_is_at_call_time(self) -> None:
        proxy = _StreamProxy("stdout")
        original_stdout = sys.stdout
        replacement = io.StringIO()
        sys.stdout = replacement
        try:
            proxy.write("hello")
            proxy.flush()
        finally:
            sys.stdout = original_stdout
        self.assertEqual("hello", replacement.getvalue())

    def test_does_not_write_to_the_stream_captured_at_construction_time(self) -> None:
        proxy = _StreamProxy("stdout")
        stale_capture = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = stale_capture
        try:
            sys.stdout = io.StringIO()  # swapped again after proxy already exists
            proxy.write("later")
        finally:
            current = sys.stdout
            sys.stdout = original_stdout
        self.assertEqual("", stale_capture.getvalue())
        self.assertEqual("later", current.getvalue())


if __name__ == "__main__":
    unittest.main()

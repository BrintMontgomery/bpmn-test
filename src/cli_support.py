"""Shared CLI entry-point skeleton for this project's argparse-based tools.

Every ``main()`` in this repository parses arguments, calls exactly one
workflow function, and reports either a single success line or an
``"error: <message>"`` line -- this factors that shape out so the CLIs stay
in lockstep instead of hand-copied.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def run_cli(
    argv: Sequence[str] | None,
    *,
    parser_factory: Callable[[], argparse.ArgumentParser],
    action: Callable[[argparse.Namespace], T],
    error_types: tuple[type[BaseException], ...],
    logger: logging.Logger,
    on_success: Callable[[T], None] | None = None,
) -> int:
    """Parse argv, run one workflow action, and report success or failure.

    ``action`` raising any of ``error_types`` is reported as a single
    ``"error: <message>"`` line on stderr and an exit code of 1. Otherwise
    ``on_success``, if given, receives the action's result before exit code 0.
    """
    args = parser_factory().parse_args(argv)
    try:
        result = action(args)
    except error_types as exc:
        logger.error(f"error: {exc}")
        return 1
    if on_success is not None:
        on_success(result)
    return 0

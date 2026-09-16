"""
NyayaOS demo console logger — prints each pipeline step clearly for viva/demo.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

# Force readable console output for the teacher demo
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("nyayaos.demo")


def banner(title: str) -> None:
    line = "=" * 72
    logger.info("\n%s\n  %s\n%s", line, title, line)


def step(n: int | str, title: str, **details: Any) -> None:
    logger.info("\n>>> STEP %s: %s", n, title)
    for key, value in details.items():
        logger.info("    • %s: %s", key, value)


def info(msg: str, **details: Any) -> None:
    logger.info("    %s", msg)
    for key, value in details.items():
        logger.info("    • %s: %s", key, value)


def success(msg: str) -> None:
    logger.info("    ✓ %s", msg)


def warn(msg: str) -> None:
    logger.info("    ! %s", msg)

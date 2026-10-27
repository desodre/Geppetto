"""Logging for Geppetto.

Every logger lives under the ``geppetto`` hierarchy (``geppetto.Device.<serial>``,
``geppetto.ADB.<serial>``, ``geppetto.Controller.<name>``) and the package root only has a
``NullHandler``: a script that configures logging itself (``logging.basicConfig``, pytest's
caplog…) receives the records as usual.

:class:`DeviceLogger` is the opt-in convenience that :class:`~geppetto.Device` uses: a
console handler and, with ``result_dir``, a log file under ``<result_dir>/Logs``. The
logger then stops propagating, so the records are not printed twice.
"""

from __future__ import annotations

import logging
from pathlib import Path

ROOT_LOGGER = "geppetto"
logging.getLogger(ROOT_LOGGER).addHandler(logging.NullHandler())


class DeviceLogger:
    """Factory for device-scoped and controller-scoped loggers."""

    #: (logger name, log file or None, console) → logger: a new result dir gets new handlers.
    _loggers: dict[tuple[str, Path | None, bool], logging.Logger] = {}

    @staticmethod
    def _build(
        name: str,
        label: str,
        log_file: Path | None,
        log_to_console: bool,
    ) -> logging.Logger:
        key = (name, log_file, log_to_console)
        if key in DeviceLogger._loggers:
            return DeviceLogger._loggers[key]

        logger = logging.getLogger(f"{ROOT_LOGGER}.{name}")
        logger.setLevel(logging.INFO)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

        formatter = logging.Formatter(
            f"[%(levelname)s] {label} [%(asctime)s] %(message)s", datefmt="%H:%M:%S"
        )
        if log_to_console:
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            logger.addHandler(console)
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        # With our own handlers, do not repeat the records through the root logger.
        logger.propagate = not logger.handlers

        DeviceLogger._loggers[key] = logger
        return logger

    @staticmethod
    def get_logger(
        main: str,
        component: str = "ADB",
        log_to_file: bool = True,
        result_dir: str | Path | None = "./results",
        log_to_console: bool = True,
    ) -> logging.Logger:
        """Logger ``geppetto.<component>.<main>``; the file goes to
        ``<result_dir>/Logs/<component>.log`` (folder created). ``result_dir=None`` or
        ``log_to_file=False`` disables the file."""
        log_file = (
            Path(result_dir) / "Logs" / f"{component.lower()}.log"
            if log_to_file and result_dir is not None
            else None
        )
        return DeviceLogger._build(
            f"{component}.{main}", f"[{component}] [{main}]", log_file, log_to_console
        )

    @staticmethod
    def get_controller_logger(
        controller_name: str,
        log_to_file: bool = True,
        result_dir: str | Path | None = "./results",
        log_to_console: bool = True,
    ) -> logging.Logger:
        log_file = (
            Path(result_dir) / "Logs" / "controller.log"
            if log_to_file and result_dir is not None
            else None
        )
        return DeviceLogger._build(
            f"Controller.{controller_name}",
            f"[Controller] [{controller_name}]",
            log_file,
            log_to_console,
        )

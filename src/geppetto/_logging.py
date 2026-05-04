from __future__ import annotations

import logging
import os
from pathlib import Path


class DeviceLogger:
    """Factory for device-scoped and controller-scoped loggers."""

    _loggers: dict[str, logging.Logger] = {}

    @staticmethod
    def get_logger(
        main: str,
        component: str = "ADB",
        log_to_file: bool = True,
        result_dir: str | Path = "./results",
    ) -> logging.Logger:
        logger_name = f"{component}.{main}"

        if logger_name in DeviceLogger._loggers:
            return DeviceLogger._loggers[logger_name]

        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if logger.handlers:
            logger.handlers.clear()

        formatter = logging.Formatter(
            f"[%(levelname)s] [{component}] [{main}] [%(asctime)s] %(message)s",
            datefmt="%H:%M:%S",
        )

        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_to_file:
            log_file = os.path.join(result_dir, "Logs", f"{component.lower()}.log")
            logger.addHandler(logging.FileHandler(log_file))
            logger.handlers[-1].setFormatter(formatter)

        DeviceLogger._loggers[logger_name] = logger
        return logger

    @staticmethod
    def get_controller_logger(
        controller_name: str,
        log_to_file: bool = True,
        result_dir: str | Path = "./results",
    ) -> logging.Logger:
        logger_name = f"Controller.{controller_name}"

        if logger_name in DeviceLogger._loggers:
            return DeviceLogger._loggers[logger_name]

        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if logger.handlers:
            logger.handlers.clear()

        formatter = logging.Formatter(
            f"[%(levelname)s] [Controller] [{controller_name}] [%(asctime)s] %(message)s",
            datefmt="%H:%M:%S",
        )

        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_to_file:
            log_dir = os.path.join(result_dir, "Logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "controller.log")
            logger.addHandler(logging.FileHandler(log_file))
            logger.handlers[-1].setFormatter(formatter)

        DeviceLogger._loggers[logger_name] = logger
        return logger

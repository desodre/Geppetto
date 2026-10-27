import logging

import pytest

from geppetto import DeviceLogger, Direction


def test_package_root_has_only_a_null_handler():
    root = logging.getLogger("geppetto")
    assert any(isinstance(h, logging.NullHandler) for h in root.handlers)


def test_log_folder_is_created(tmp_path):
    logger = DeviceLogger.get_logger(
        "S1", "Acroname", result_dir=tmp_path / "novo", log_to_console=False
    )
    logger.info("oi")
    assert (tmp_path / "novo" / "Logs" / "acroname.log").read_text().strip().endswith("oi")


def test_a_new_result_dir_gets_its_own_file(tmp_path):
    DeviceLogger.get_logger(
        "S2", "Device", result_dir=tmp_path / "run1", log_to_console=False
    ).info("um")
    DeviceLogger.get_logger(
        "S2", "Device", result_dir=tmp_path / "run2", log_to_console=False
    ).info("dois")
    assert "dois" not in (tmp_path / "run1" / "Logs" / "device.log").read_text()
    assert "dois" in (tmp_path / "run2" / "Logs" / "device.log").read_text()


def test_without_handlers_records_propagate(caplog):
    logger = DeviceLogger.get_logger("S3", "Device", result_dir=None, log_to_console=False)
    with caplog.at_level("INFO"):
        logger.info("chega no caplog")
    assert "chega no caplog" in caplog.text


def test_direction_keeps_the_old_names():
    assert Direction.Up is Direction.UP and Direction.Down is Direction.DOWN


def test_colors_are_all_distinct():
    pytest.importorskip("imagehash")
    from geppetto.analyzers.screen import Colors

    assert len(Colors) == 6
    assert len({c.value for c in Colors}) == 6

import inspect
from pathlib import Path

import pytest

from geppetto._deprecation import warn_deprecated


def test_warning_points_to_the_user_call_and_explains_migration():
    def old_api():
        warn_deprecated("old_api()", "new_api()", "2.2.0")

    with pytest.warns(DeprecationWarning, match=r"old_api\(\).*2.2.0.*new_api\(\)") as caught:
        call_line = inspect.currentframe().f_lineno + 1
        old_api()
    assert Path(caught[0].filename) == Path(__file__)
    assert caught[0].lineno == call_line
    assert "at least one minor release" in str(caught[0].message)
    assert "only in a major" in str(caught[0].message)


def test_existing_direction_aliases_still_work_without_warnings():
    import warnings

    from geppetto import Direction

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert Direction.Up is Direction.UP
        assert Direction.Down is Direction.DOWN
    assert not caught

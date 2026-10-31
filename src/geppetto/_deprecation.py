"""Consistent warnings called from the deprecated public API itself."""

import warnings


def warn_deprecated(old: str, new: str, since: str) -> None:
    """Warn at the user's call site; retain the API for a minor and remove only in a major."""
    warnings.warn(
        f"{old} is deprecated since {since}; use {new} instead. "
        "It will remain available for at least one minor release and be removed only in a major.",
        DeprecationWarning,
        stacklevel=3,
    )

"""Helpers for resolving the package version in development and runtime."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path
from typing import Final

_PYPROJECT_PATH: Final = Path("pyproject.toml")


def get_version_from_metadata() -> str:
    """Return the version published in the installed package metadata."""
    return metadata.version(__package__ or __name__)


def get_version_from_pyproject() -> str:
    """Return the version declared in ``pyproject.toml`` for local builds."""
    data = tomllib.loads(_PYPROJECT_PATH.read_text("utf-8"))
    return str(data["project"]["version"])


def get_version() -> str:
    """Return the version from metadata or ``pyproject.toml`` as a fallback."""
    try:
        return get_version_from_metadata()
    except metadata.PackageNotFoundError:
        try:
            return get_version_from_pyproject()
        except (FileNotFoundError, KeyError):
            return "unknown"


__version__: Final = get_version()

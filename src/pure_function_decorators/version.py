"""Helpers for retrieving the project version at runtime."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

import tomllib

_PYPROJECT_PATH = Path("pyproject.toml")


def get_version_from_metadata() -> str:
    """Return the version declared in installed package metadata."""

    return metadata.version(__package__ or __name__)


def get_version_from_pyproject(path: Path = _PYPROJECT_PATH) -> str:
    """Return the version declared in a ``pyproject.toml`` file."""

    data = tomllib.loads(path.read_text("utf-8"))
    return str(data["project"]["version"])


def get_version(path: Path = _PYPROJECT_PATH) -> str:
    """Return the version from package metadata or the ``pyproject.toml`` file."""

    try:
        return get_version_from_metadata()
    except metadata.PackageNotFoundError:
        try:
            return get_version_from_pyproject(path)
        except (FileNotFoundError, KeyError):
            return "unknown"


__version__ = get_version()

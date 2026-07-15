"""NEETML public package metadata."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("neetml")
except PackageNotFoundError:
    __version__ = "unknown"

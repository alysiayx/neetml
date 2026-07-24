"""Configuration and path handling for NEETML."""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "configs" / "default_config.yaml"
logger = logging.getLogger(__name__)


def _read_yaml(path: Path, *, required: bool = False) -> dict[str, Any]:
    """Read a YAML mapping; return an empty mapping for a missing optional file."""
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Configuration file does not exist: {path}")
        return {}

    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must contain a YAML mapping: {path}")
    return config


def _merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge nested user values into defaults without changing either input.

    Example
    -------
    Input: ``base={"data": {"file": "default.parquet", "dir": "data"}}``
    and ``override={"data": {"file": "data.parquet"}}``
    Output: ``{"data": {"file": "data.parquet", "dir": "data"}}``
    """
    merged = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve(root: Path, value: str | Path) -> Path:
    """Resolve relative values from the configured project root.

    Example
    -------
    Input: ``root=Path("/study")``, ``value="data/raw"``
    Output: ``Path("/study/data/raw")``
    """
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


class NEETMLConfig:
    """Combine repository defaults with optional user settings.

    User settings override defaults. Explicit function arguments and environment
    variables can temporarily override the merged configuration.
    """

    def __init__(
        self,
        *,
        default_config_path: Path,
        user_config_path: Path,
        config: dict[str, Any],
        user_config: dict[str, Any],
        project_root: Path,
    ) -> None:
        self.default_config_path = default_config_path
        self.user_config_path = user_config_path
        self._config = config
        self._user_config = user_config
        self.project_root = project_root

    @classmethod
    def load(
        cls,
        *,
        project_root: str | Path | None = None,
        default_config_path: str | Path | None = None,
        user_config_path: str | Path | None = None,
    ) -> "NEETMLConfig":
        """Load defaults and apply an optional user configuration.

        Example
        -------
        Input: defaults use ``longitudinal.parquet`` and the user config uses
        ``data.parquet``.
        Output: a config object whose model-input path ends in
        ``data.parquet``.
        """
        default_path = Path(default_config_path or DEFAULT_CONFIG_PATH).expanduser().resolve()
        defaults = _read_yaml(default_path, required=True)
        repo_root = default_path.parent.parent.parent

        root_override = project_root or os.getenv("NEETML_PROJECT_ROOT")
        config_root = _resolve(repo_root, root_override or ".")
        user_path = Path(
            user_config_path
            or os.getenv("NEETML_USER_CONFIG")
            or config_root / ".neetml" / "config.yaml"
        ).expanduser().resolve()

        user_config = _read_yaml(user_path)
        config = _merge(defaults, user_config)
        saved_root = config.get("project", {}).get("root", ".")
        root = _resolve(repo_root, root_override or saved_root)

        return cls(
            default_config_path=default_path,
            user_config_path=user_path,
            config=config,
            user_config=user_config,
            project_root=root,
        )

    @property
    def config(self) -> dict[str, Any]:
        """Return a copy of the active configuration.

        Example
        -------
        Input: merged defaults and user settings held by this object.
        Output: an independent dictionary that callers may inspect safely.
        """
        return copy.deepcopy(self._config)

    def _config_path(self, name: str, seen: frozenset[str] = frozenset()) -> Path:
        """Resolve a configured path and any parent path it references.

        Example
        -------
        Input: ``data_dir="data"`` and
        ``processed_dir={"base": "data_dir", "path": "02_processed"}``.
        Output for ``processed_dir``: ``<project>/data/02_processed``.
        """
        if name in seen:
            chain = " -> ".join([*seen, name])
            raise ValueError(f"Circular configured path reference: {chain}")
        try:
            value = self._config["paths"][name]
        except KeyError as error:
            raise KeyError(f"Unknown configured path: {name!r}") from error

        if not isinstance(value, Mapping):
            return _resolve(self.project_root, value)
        if "base" not in value or "path" not in value:
            raise KeyError(f"Configured path {name!r} must define 'base' and 'path'")

        base = self._config_path(str(value["base"]), seen | {name})
        return _resolve(base, value["path"])

    def _get_path(
        self,
        name: str,
        *,
        path: str | Path | None = None,
        env_var: str | None = None,
    ) -> Path:
        """Resolve one project root, config file, folder or dataset key.

        Example
        -------
        Input: dataset ``{"dir": "processed_dir", "file": "data.parquet"}``.
        Output: ``<project>/data/02_processed/data.parquet``.
        """
        if path is not None:
            return _resolve(self.project_root, path)
        if name == "project_root":
            return self.project_root
        if name == "user_config":
            return self.user_config_path
        if name in self._config.get("paths", {}):
            env_value = os.getenv(env_var or f"NEETML_{name.upper()}")
            return _resolve(self.project_root, env_value) if env_value else self._config_path(name)
        if name in self._config.get("datasets", {}):
            env_value = os.getenv(env_var or f"NEETML_{name.upper()}_PATH")
            if env_value:
                return _resolve(self.project_root, env_value)
            dataset = self._config["datasets"][name]
            try:
                data_dir = dataset["dir"]
                filename = dataset["file"]
            except KeyError as error:
                raise KeyError(f"Incomplete dataset: {name!r}") from error
            if data_dir in self._config.get("paths", {}):
                data_dir = self._config_path(data_dir)
            else:
                data_dir = _resolve(self.project_root, data_dir)
            return data_dir / filename
        raise KeyError(f"Unknown path or dataset: {name!r}")

    def profile(self, name: str) -> dict[str, Any]:
        """Return a profile such as ``sample`` or ``real``.

        Example
        -------
        Input: ``profile("real")``.
        Output: ``{"dataset": "model_input", "output": "real"}``.
        """
        try:
            return copy.deepcopy(self._config["profiles"][name])
        except KeyError as error:
            raise KeyError(f"Unknown data profile: {name!r}") from error

    def get_path(
        self,
        keys: str | Iterable[str] = "all",
        *,
        path: str | Path | None = None,
        env_var: str | None = None,
        as_dict: bool = False,
    ):
        """Resolve one key or display several paths.

        A single key returns ``Path``; a list or ``"all"`` returns a table.

        Examples
        --------
        Input: ``get_path("model_input")``.
        Output: one complete ``Path`` to the modelling dataset.

        Input: ``get_path("all")``.
        Output: a table containing every configured path and dataset.
        """
        if isinstance(keys, str) and keys != "all" and not as_dict:
            return self._get_path(
                keys,
                path=path,
                env_var=env_var,
            )
        if path is not None or env_var is not None:
            raise ValueError("path and env_var require one path key")

        entries: dict[str, tuple[Path, str]] = {
            "project_root": (self.project_root, "Configured project root"),
            "user_config": (self.user_config_path, "User configuration"),
        }
        entries.update(
            (name, (self._get_path(name), "Configured path"))
            for name in self._config.get("paths", {})
        )
        entries.update(
            (name, (self._get_path(name), "Configured dataset"))
            for name in self._config.get("datasets", {})
        )

        names = list(entries) if keys == "all" else [keys] if isinstance(keys, str) else list(keys)
        unknown = sorted(set(names) - set(entries))
        if unknown:
            raise ValueError(f"Unknown path key(s): {unknown}")

        selected = {name: entries[name] for name in names}
        if as_dict:
            return {
                name: {"path": path, "description": description}
                for name, (path, description) in selected.items()
            }

        import pandas as pd

        return pd.DataFrame(
            {"Type": name, "Path": path, "Description": description}
            for name, (path, description) in selected.items()
        )

    def update(
        self,
        *,
        project_root: str | Path | None = None,
        data_dir: str | Path | None = None,
        paths: Mapping[str, str | Path] | None = None,
        dataset: str | None = None,
        folder: str | Path | None = None,
        filename: str | None = None,
        year_range: tuple[int, int] | None = None,
    ) -> "NEETMLConfig":
        """Apply user settings; call ``save()`` to persist them.

        Example
        -------
        Input: ``update(dataset="model_input", folder="processed_dir",
        year_range=(2018, 2026))``.
        Output in memory: ``model_input`` points to
        ``processed_dir/2018-2026.parquet``.
        """
        options = (folder, filename, year_range)
        if any(value is not None for value in options) and dataset is None:
            raise ValueError("dataset is required for dataset-specific settings")
        if dataset is not None and not any(
            value is not None for value in options
        ):
            raise ValueError("Provide folder, filename or year_range")
        if filename is not None and year_range is not None:
            raise ValueError("Choose either filename or year_range, not both")
        if not any(
            value is not None
            for value in (project_root, data_dir, paths, dataset, *options)
        ):
            raise ValueError("No configuration values were provided")

        update: dict[str, Any] = {}
        changes: list[str] = []
        if project_root is not None:
            root = Path(project_root).expanduser().resolve()
            update["project"] = {"root": str(root)}
            self.project_root = root
            changes.append(f"project_root={root}")

        path_updates = dict(paths or {})
        if data_dir is not None:
            path_updates["data_dir"] = data_dir
        if path_updates:
            update["paths"] = {
                name: str(value) for name, value in path_updates.items()
            }
            changes.extend(
                f"{name}={value}" for name, value in update["paths"].items()
            )

        if dataset is not None and any(value is not None for value in options):
            if year_range is not None:
                if (
                    not isinstance(year_range, tuple)
                    or len(year_range) != 2
                    or not all(isinstance(year, int) for year in year_range)
                    or year_range[0] > year_range[1]
                ):
                    raise ValueError("year_range must contain two increasing integer years")
                filename = f"{year_range[0]}-{year_range[1]}.parquet"
            if filename is not None:
                if Path(filename).name != filename:
                    raise ValueError("filename must not include a folder")
                if Path(filename).suffix.lower() != ".parquet":
                    raise ValueError("dataset filenames must use .parquet")

            dataset_config: dict[str, str] = {}
            if folder is not None:
                dataset_config["dir"] = str(folder)
            if filename is not None:
                dataset_config["file"] = filename
            update["datasets"] = {dataset: dataset_config}
            changes.extend(
                f"{dataset}.{name}={value}"
                for name, value in dataset_config.items()
            )

        self._user_config = _merge(self._user_config, update)
        self._config = _merge(self._config, update)
        logger.info("Updated user configuration: %s", ", ".join(changes))
        return self

    def save(self) -> Path:
        """Write user settings without changing the repository defaults.

        Example
        -------
        Input: unsaved user settings held in memory.
        Output: ``<project>/.neetml/config.yaml`` and its ``Path``.
        """
        self.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.user_config_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(self._user_config, handle, sort_keys=False)
        logger.info("Saved user configuration: %s", self.user_config_path)
        return self.user_config_path

    def reset(self) -> "NEETMLConfig":
        """Delete user settings and restore repository defaults.

        Environment variables remain active because they are temporary overrides,
        not values stored in the user configuration.

        Example
        -------
        Input: a project containing ``.neetml/config.yaml`` overrides.
        Output: the file is removed and this object again uses repository defaults.
        """
        removed = self.user_config_path.exists()
        if removed:
            self.user_config_path.unlink()

        defaults = _read_yaml(self.default_config_path, required=True)
        self._user_config = {}
        self._config = defaults
        repo_root = self.default_config_path.parent.parent.parent
        root = os.getenv("NEETML_PROJECT_ROOT") or defaults.get("project", {}).get("root", ".")
        self.project_root = _resolve(repo_root, root)
        logger.info(
            "Reset user configuration%s; restored repository defaults",
            f" and removed {self.user_config_path}" if removed else "",
        )
        return self

from pathlib import Path

from .config import NEETMLConfig

# ------------------------------- init + getters -----------------------------
_DATA_ROOT: Path | None = None
_PATHS: dict[str, Path] = {}

def _reset_all():
    global _DATA_ROOT, _PATHS
    _DATA_ROOT = None
    _PATHS.clear()

def init(
    root: str | Path | None = None,
    *,
    force: bool = False,
    create: bool = False,
) -> None:
    global _DATA_ROOT, _PATHS
    if _DATA_ROOT and not force:
        return
    
    if force:
        _reset_all()

    settings = NEETMLConfig.load(project_root=root)
    _DATA_ROOT = settings.project_root

    _PATHS = {
        "DATA_DIR": settings.get_path("data_dir"),
        "SRC_DATA_DIR": settings.get_path("raw_dir"),
        "SRC_META_DIR": settings.get_path("raw_meta_dir"),
        "EXT_DATA_DIR": settings.get_path("external_dir"),
        "SRC_COLSTD_DIR": settings.get_path("interim_dir"),
        "PROC_DATA_DIR": settings.get_path("processed_dir"),
        "FILE_METADATA_PATH": settings.get_path("file_meta_path"),
        "COL_METADATA_PATH": settings.get_path("col_meta_path"),
        "CLEAN_DIR": settings.get_path("cleaned_dir"),
        "MERGE_DIR": settings.get_path("merged_dir"),
        "LINK_DIR": settings.get_path("linked_dir"),
        "DERIVE_DIR": settings.get_path("derived_dir"),
        "AGG_DIR": settings.get_path("aggregated_dir"),
        "PROFILE_DIR": settings.get_path("profile_dir"),
    }

    for k, v in _PATHS.items():
        globals()[k] = v
        if create:
            v.mkdir(parents=True, exist_ok=True)

def reset(root: str | Path | None = None) -> None:
    """Hard reset the data root no matter what."""
    _reset_all()
    init(root)

def p(key: str) -> Path:
    if _DATA_ROOT is None:
        init()
    return _PATHS[key]

def __getattr__(name: str):
    if name in _PATHS:
        return p(name)
    raise AttributeError(name)

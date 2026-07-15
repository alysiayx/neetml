from pathlib import Path
import os

# ------------------------------- init + getters -----------------------------
_DATA_ROOT: Path | None = None
_PATHS: dict[str, Path] = {}

def _reset_all():
    global _DATA_ROOT, _PATHS
    _DATA_ROOT = None
    _PATHS.clear()

def init(root: str | Path | None = None, *, force: bool = False) -> None:
    global _DATA_ROOT, _PATHS
    if _DATA_ROOT and not force:
        return
    
    if force:
        _reset_all()

    root = Path(root or os.getenv("NEETML_DATA_DIR") or ".").expanduser().resolve()
    _DATA_ROOT = root

    _PATHS = {
        "SRC_DATA_DIR"  : root / "00_source",
        "SRC_META_DIR"  : root / "00_source_meta",
        "EXT_DATA_DIR"  : root / "00_external",
        "SRC_COLSTD_DIR": root / "01_source_colstd",
        "PROC_DATA_DIR" : root / "02_processed",
    }
    _PATHS.update({
        "CLEAN_DIR" : _PATHS["PROC_DATA_DIR"] / "1_cleaned",
        "MERGE_DIR" : _PATHS["PROC_DATA_DIR"] / "2_merged",
        "AGG_DIR"   : _PATHS["PROC_DATA_DIR"] / "3_aggregated",
    })
    
    # for p in _PATHS.values(): p.mkdir(parents=True, exist_ok=True)
    for k, v in _PATHS.items():
        globals()[k] = v
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
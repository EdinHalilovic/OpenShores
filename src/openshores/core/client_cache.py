
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


_HAZERON_CACHE_DIR_CANDIDATES = [
    Path(os.environ.get("USERPROFILE", "C:/")) / "Shores of Hazeron" / "Temporary",
    Path(os.environ.get("USERPROFILE", "C:/")) / "Shores of Hazeron",
    Path(os.environ.get("USERPROFILE", "C:/")) / "Documents" / "Hazeron Caches",
    Path(os.environ.get("USERPROFILE", "C:/")) / "Documents" / "Hazeron",
    Path(os.environ.get("APPDATA", "C:/"))     / "Hazeron"  / "Caches",
    Path(os.environ.get("APPDATA", "C:/"))     / "Hazeron",
    Path(os.environ.get("LOCALAPPDATA", "C:/"))/ "Hazeron"  / "Caches",
    Path(os.environ.get("LOCALAPPDATA", "C:/"))/ "Hazeron",
]


def _find_planet_cache_dir(template_auid_dec: int) -> Optional[Path]:
    pat_specific_wtf = f"WTF{template_auid_dec}X*"
    pat_any_wtf = "WTF*X*"
    pat_specific_wgf = f"WGF{template_auid_dec}"
    pat_any_wgf = "WGF*"
    for d in _HAZERON_CACHE_DIR_CANDIDATES:
        try:
            if d.exists() and (
                next(iter(d.glob(pat_specific_wtf)), None)
                or (d / pat_specific_wgf).exists()
            ):
                return d
        except OSError:
            continue
    for d in _HAZERON_CACHE_DIR_CANDIDATES:
        try:
            if d.exists() and (
                next(iter(d.glob(pat_any_wtf)), None)
                or next(iter(d.glob(pat_any_wgf)), None)
            ):
                return d
        except OSError:
            continue
    return None


def _pick_template_files(
    cache_dir: Path,
    template_auid_dec: int,
) -> tuple[list[Path], Optional[Path]]:
    wtfs: list[Path] = []
    try:
        wtfs = list(cache_dir.glob(f"WTF{template_auid_dec}X*"))
    except OSError:
        wtfs = []
    if not wtfs:
        try:
            wtfs = list(cache_dir.glob("WTF*X*"))
        except OSError:
            wtfs = []
    wgf: Optional[Path] = None
    spec_wgf = cache_dir / f"WGF{template_auid_dec}"
    if spec_wgf.exists():
        wgf = spec_wgf
    else:
        try:
            wgf = next(iter(cache_dir.glob("WGF*")), None)
        except OSError:
            wgf = None
    return (wtfs, wgf)

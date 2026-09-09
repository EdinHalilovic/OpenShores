
from __future__ import annotations

from pathlib import Path
from typing import Optional

from openshores.gameplay.worldgen.globe_divisions import _GLOBE_DIVISIONS_LUT


def _extract_size_suffix(filename: str) -> str:
    if not filename.startswith("WTF"):
        return ""
    body = filename[3:]
    x = body.rfind("X")
    if x <= 0:
        return ""
    return body[x:]


def _extract_size_int(filename: str) -> Optional[int]:
    suf = _extract_size_suffix(filename)
    if not suf or not suf[1:].isdigit():
        return None
    return int(suf[1:])


def _planet_cache_filename_size(
    target_size_byte: Optional[int],
    multiplier: Optional[int],
) -> Optional[int]:
    if target_size_byte is None or multiplier is None:
        return None
    base = _GLOBE_DIVISIONS_LUT.get(target_size_byte)
    if base is None:
        return None
    return base * multiplier


def _detect_size_multiplier(
    template_wtfs: list[Path],
    template_size_byte: Optional[int],
) -> Optional[int]:
    if template_size_byte is None:
        return None
    base = _GLOBE_DIVISIONS_LUT.get(template_size_byte)
    if not base:
        return None
    for p in template_wtfs:
        sz = _extract_size_int(p.name)
        if sz is None or sz <= 0:
            continue
        if sz % base == 0:
            return sz // base
    return None



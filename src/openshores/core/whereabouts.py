from __future__ import annotations

import argparse
import logging
import sys
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


_CANDIDATE_BASES = [
    r"Software\Shores of Hazeron",
    r"Software\ShoresOfHazeron",
    r"Software\QtProject\OrganizationDefaults",
    r"Software\Shores of Hazeron.exe",
]


# Wrote some shitty stuff in case we need to check for non-wine linux
def _winreg():
    if sys.platform not in ("win32",):
        return None
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def find_whereabouts_subkeys(
        root_path: str = r"Software",
        max_depth: int = 6,
        verbose: bool = False) -> List[Tuple[str, List[Tuple[str, object]]]]:
    winreg = _winreg()
    results: List[Tuple[str, List[Tuple[str, object]]]] = []
    if winreg is None:
        if verbose:
            logger.info("[whereabouts-reg] not on Windows; nothing to do")
        return results

    stack: List[Tuple[str, int]] = [(root_path, 0)]
    visited = 0
    while stack:
        path, depth = stack.pop()
        visited += 1
        try:
            k = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            continue
        try:
            i = 0
            subs = []
            while True:
                try:
                    name = winreg.EnumKey(k, i)
                except OSError:
                    break
                subs.append(name)
                i += 1
            for sub in subs:
                full = path + "\\" + sub
                if sub.lower() == "whereabouts":
                    vals = _dump_values(winreg, full)
                    results.append((full, vals))
                    if verbose:
                        logger.info("[whereabouts-reg] FOUND HKCU\\" + full
                              + "  (" + str(len(vals)) + " value(s))")
                        for n, v in vals:
                            if isinstance(v, str) and len(v) > 160:
                                v_s = v[:157] + "..."
                            else:
                                v_s = v
                            logger.info("    " + repr(n) + " = " + repr(v_s))
                if depth + 1 < max_depth:
                    stack.append((full, depth + 1))
        finally:
            winreg.CloseKey(k)

    if verbose:
        logger.info("[whereabouts-reg] scanned " + str(visited)
              + " keys under HKCU\\" + root_path
              + "; " + str(len(results)) + " Whereabouts subkey(s) found")
    return results


def _dump_values(winreg, path: str) -> List[Tuple[str, object]]:
    try:
        k = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        return []
    vals: List[Tuple[str, object]] = []
    try:
        i = 0
        while True:
            try:
                name, data, _t = winreg.EnumValue(k, i)
            except OSError:
                break
            vals.append((name, data))
            i += 1
    finally:
        winreg.CloseKey(k)
    return vals


def probe_bases(verbose: bool = False) -> List[str]:
    winreg = _winreg()
    if winreg is None:
        if verbose:
            logger.info("[whereabouts-reg] not running on Windows; nothing to do")
        return []
    hits: List[str] = []
    for base in _CANDIDATE_BASES:
        try:
            k = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, base)
        except OSError:
            if verbose:
                logger.info("[whereabouts-reg] absent  HKCU\\" + base)
            continue
        hits.append(base)
        if verbose:
            logger.info("[whereabouts-reg] PRESENT HKCU\\" + base)
            try:
                i = 0
                while True:
                    name, value, _t = winreg.EnumValue(k, i)
                    i += 1
                    if isinstance(value, str) and len(value) > 120:
                        value = value[:117] + "..."
                    logger.info("    value  " + repr(name) + " = " + repr(value))
            except OSError as exc:
                logger.debug("[whereabouts-reg] value enumeration ended at "
                             "index %d: %r", i, exc)
            try:
                wk = winreg.OpenKeyEx(
                    winreg.HKEY_CURRENT_USER, base + r"\Whereabouts")
                logger.info("    (Whereabouts subkey PRESENT)")
                j = 0
                while True:
                    try:
                        name, data, _t = winreg.EnumValue(wk, j)
                    except OSError:
                        break
                    logger.info("      "
                          + repr(name) + " = " + repr(data))
                    j += 1
                winreg.CloseKey(wk)
            except OSError:
                logger.info("    (no Whereabouts subkey)")
        winreg.CloseKey(k)
    return hits


def string_id(auid: int) -> str:
    n = int(auid) & 0xFFFFFFFF
    out = []
    while True:
        out.append(chr(ord("A") + (n % 26)))
        n //= 26
        if n == 0:
            return "".join(out)


def write_whereabouts_all(username: str,
                          whereabouts: str,
                          *,
                          bases: Optional[Iterable[str]] = None,
                          verbose: bool = False) -> int:
    winreg = _winreg()
    if winreg is None:
        if verbose:
            logger.info("[whereabouts-reg] non-Windows platform. Skipping")
        return 0

    if bases is None:
        bases = _CANDIDATE_BASES
    n_written = 0
    for base in bases:
        sub = base + r"\Whereabouts"
        try:
            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, sub,
                0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, username, 0, winreg.REG_SZ, whereabouts)
            winreg.CloseKey(key)
            n_written += 1
            if verbose:
                logger.info("[whereabouts-reg] wrote HKCU\\" + sub + "\\"
                      + username + " = " + repr(whereabouts))
        except OSError as exc:
            if verbose:
                logger.warning("[whereabouts-reg] FAILED HKCU\\" + sub + ": "
                      + repr(exc))
    return n_written


def main() -> int:
    p = argparse.ArgumentParser(
        description="Probe/seed the SoH client QSettings Whereabouts cache")
    p.add_argument("--find", action="store_true",
                   help="recursively search HKCU\\Software for any "
                        "'Whereabouts' subkey (authoritative discovery)")
    p.add_argument("--probe", action="store_true",
                   help="check the known candidate registry bases")
    p.add_argument("--user",
                   help="account username (required to write)")
    p.add_argument("--value",
                   help='location string to display, e.g. "On OAZ\'WC\'EE\'a Vb"')
    p.add_argument("--base",
                   help="restrict write to a single specific HKCU subkey "
                        "path (e.g. 'Software\\Shores of Hazeron'). "
                        "Overrides the default candidate-base list.")
    args = p.parse_args()

    if not (args.find or args.probe) and (args.user and args.value):
        bases = [args.base] if args.base else None
        n = write_whereabouts_all(
            args.user, args.value, bases=bases, verbose=True)
        logger.info("\nwrote whereabouts to " + str(n) + " registry base(s)")
        return 0 if n > 0 else 1

    did_something = False
    if args.find:
        results = find_whereabouts_subkeys(verbose=True)
        logger.info("\n" + str(len(results))
              + " Whereabouts subkey(s) found under HKCU\\Software")
        for path, vals in results:
            logger.info("  HKCU\\" + path + "  (" + str(len(vals)) + " value(s))")
        did_something = True
    if args.probe:
        hits = probe_bases(verbose=True)
        logger.info("\n" + str(len(hits)) + " candidate base(s) present under HKCU")
        did_something = True
    if args.user and args.value:
        bases = [args.base] if args.base else None
        n = write_whereabouts_all(
            args.user, args.value, bases=bases, verbose=True)
        logger.info("\nwrote whereabouts to " + str(n) + " registry base(s)")
        did_something = True

    if not did_something:
        p.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

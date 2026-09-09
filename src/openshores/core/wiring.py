
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Hashable, Mapping


_PROBE = object()


def requirements(fn: Callable[..., Any]) -> tuple[str, ...]:
    return tuple(
        name for name, p in inspect.signature(fn).parameters.items()
        if p.kind is p.KEYWORD_ONLY and p.default is p.empty)


def _defaulted(fn: Callable[..., Any]) -> tuple[str, ...]:
    return tuple(
        name for name, p in inspect.signature(fn).parameters.items()
        if p.kind is p.KEYWORD_ONLY and p.default is not p.empty)


def bind(handlers: Mapping[Hashable, Callable[..., Any]],
         providers: Mapping[str, Any],
         *,
         expect: set) -> dict:
    missing_keys = sorted(k for k in expect if k not in handlers)
    problems: list[str] = []
    if missing_keys:
        problems.append(
            "no handler registered for: "
            + ", ".join(_show(k) for k in missing_keys)
            + " -- a module that nobody imports registers nothing")

    routes: dict = {}
    for key in sorted(handlers, key=_show):
        fn = handlers[key]
        optional = _defaulted(fn)
        if optional:
            problems.append(
                f"{_show(key)} -> {_name(fn)} declares keyword-only "
                f"{list(optional)} WITH a default; a dependency that can be "
                f"skipped is not a dependency")
            continue
        need = requirements(fn)
        absent = [n for n in need if n not in providers]
        if absent:
            problems.append(
                f"{_show(key)} -> {_name(fn)} needs {absent}, "
                f"which no provider supplies")
            continue
        route = fn if not need else functools.partial(
            fn, **{n: providers[n] for n in need})
        try:
            inspect.signature(route).bind(_PROBE, b"")
        except TypeError as exc:
            problems.append(
                f"{_show(key)} -> {_name(fn)} is not callable as "
                f"(session, payload) once bound: {exc}")
            continue
        routes[key] = route

    if problems:
        raise KeyError("; ".join(problems))
    return routes


def _show(key: Any) -> str:
    return f"0x{key:02X}" if isinstance(key, int) else repr(key)


def _name(fn: Callable[..., Any]) -> str:
    return getattr(fn, "__qualname__", None) or repr(fn)

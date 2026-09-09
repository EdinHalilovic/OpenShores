
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


DEFAULT_LOGIN_PORT = 16757
DEFAULT_CHAT_PORT = 16758
DEFAULT_SCENE_PORT = 16759
DEFAULT_MAIL_PORT = 16760

DEFAULT_CITY_CYCLE_SECONDS = 5400 / 7


@dataclass(frozen=True)
class Deployment:

    database_url: str = "postgresql://localhost/openshores"

    bind_host: str = "0.0.0.0"

    login_port: int = DEFAULT_LOGIN_PORT
    chat_port: int = DEFAULT_CHAT_PORT
    scene_port: int = DEFAULT_SCENE_PORT
    mail_port: int = DEFAULT_MAIL_PORT

    public_host: str = "127.0.0.1"

    gd_path: Path | None = None

    cache_dir: Path = Path("cache")

    log_level: str = "INFO"

    log_file: str = "server_console.log"

    metrics_port: int = 0


    scene_probe: str = "none"

    show_acks: bool = False

    pid_file: str = "server.pid"

    control_port: int = 16761

    chat_log: bool = False
    chat_log_channels: str = "Galactic"
    chat_log_keep: int = 200

    report_dir: str = "city_reports"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None,
                 base: dict[str, object] | None = None) -> Deployment:
        env = os.environ if env is None else env
        kwargs: dict[str, object] = dict(base or {})
        for f in fields(cls):
            raw = env.get(f"OPENSHORES_{f.name.upper()}")
            if raw is None:
                continue
            kwargs[f.name] = _coerce(f.type, raw, f.name)
        return cls(**kwargs)


@dataclass(frozen=True)
class Gameplay:

    galaxy_seed: int = 0

    city_cycle_seconds: float = DEFAULT_CITY_CYCLE_SECONDS

    corpse_linger_seconds: float = 2.0

    hot_state_flush_seconds: float = 5.0


@dataclass(frozen=True)
class Config:
    deployment: Deployment = field(default_factory=Deployment)
    gameplay: Gameplay = field(default_factory=Gameplay)

    @classmethod
    def use(cls, path: str | Path | None) -> None:
        """Name the settings file for the rest of the process.

        `--config` would otherwise reach only the boot config. `find_gd` and
        anything else that calls `load()` with no argument would go on reading
        the working directory, and the process would disagree with itself about
        which file it was configured from.

        Only `__main__` calls this. Tests pass an explicit path instead, so a
        test cannot leave a setting behind for the next one.
        """
        global _NAMED_PATH
        _NAMED_PATH = Path(path) if path else None

    @classmethod
    def load(cls, path: str | Path | None = None,
             env: dict[str, str] | None = None) -> Config:
        gameplay = Gameplay()
        deployment_kwargs: dict[str, object] = {}

        toml_path = Path(path) if path else (_NAMED_PATH or Path("openshores.toml"))
        if toml_path.exists():
            with toml_path.open("rb") as fh:
                data = tomllib.load(fh)
            gameplay = Gameplay(**_section(
                toml_path, data, "gameplay", Gameplay))
            deployment_kwargs = _section(
                toml_path, data, "deployment", Deployment)

        # The environment wins over the file, so one run can be pointed at a
        # different database without editing anything.
        deployment = Deployment.from_env(env, base=deployment_kwargs)
        return cls(deployment=deployment, gameplay=gameplay)


#: The settings file `--config` named, or None for openshores.toml here.
_NAMED_PATH: Path | None = None

def _section(toml_path: Path, data: dict, name: str, cls) -> dict:
    """One TOML table, coerced, with unknown keys refused.

    Refusing is the point. A typo in a setting name is otherwise a value that
    silently keeps its default, and the operator has no way to tell that from
    the setting not working.
    """
    section = data.get(name, {})
    known = {f.name: f for f in fields(cls)}
    unknown = sorted(set(section) - set(known))
    if unknown:
        raise ValueError(
            f"{toml_path}: unknown setting(s) in [{name}]: "
            f"{', '.join(unknown)}. Known settings are: "
            f"{', '.join(sorted(known))}.")
    return {k: _coerce(known[k].type, v, k) for k, v in section.items()}


def _coerce(declared: object, raw: object, name: str):
    text = declared if isinstance(declared, str) else getattr(
        declared, "__name__", str(declared))

    if "Path" in text and "None" in text:
        return Path(str(raw)) if raw not in ("", None) else None
    if text.startswith("Path"):
        return Path(str(raw))
    if text.startswith("int"):
        try:
            return int(str(raw), 0)
        except ValueError:
            raise ValueError(f"{name}: expected an integer, got {raw!r}") from None
    if text.startswith("float"):
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{name}: expected a number, got {raw!r}") from None
    if text.startswith("bool"):
        s = str(raw).strip().lower()
        if s in ("1", "yes", "true", "on", "y", "t"):
            return True
        if s in ("0", "no", "false", "off", "n", "f", ""):
            return False
        raise ValueError(f"{name}: expected a boolean, got {raw!r}")
    return str(raw)


# pragma: no cover

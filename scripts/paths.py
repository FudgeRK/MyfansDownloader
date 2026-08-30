"""Resolve config, download, and log paths for local and Docker use."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent


def _is_docker() -> bool:
    if os.path.isfile("/.dockerenv"):
        return True
    dockerenv = os.getenv("RUNNING_IN_DOCKER", "").strip().lower()
    return dockerenv in {"1", "true", "yes"}


def config_dir() -> Path:
    env = os.getenv("CONFIG_DIR")
    if env:
        return Path(env)
    if _is_docker() and Path("/config").is_dir():
        return Path("/config")
    return ROOT


def downloads_dir(configured: Optional[str] = None) -> Path:
    env = os.getenv("DOWNLOADS_DIR")
    if env:
        return Path(env)
    if configured:
        return Path(normalize_output_dir(configured))
    if _is_docker() and Path("/downloads").is_dir():
        return Path("/downloads")
    return ROOT / "downloads"


def normalize_output_dir(path: str) -> str:
    """Map Docker-style absolute paths to a local folder when not in Docker."""
    if not path:
        return str(ROOT / "downloads")
    posix = path.replace("\\", "/")
    if posix in {"/downloads", "downloads"} and not _is_docker():
        return str((ROOT / "downloads").resolve())
    if posix.startswith("/") and os.name == "nt" and not _is_docker():
        if len(path) >= 2 and path[1] == ":":
            return path
        return str((ROOT / "downloads").resolve())
    return path


def _existing(candidates: Iterable[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_header_file(filename: str = "header.txt") -> Path:
    found = _existing(
        [
            config_dir() / filename,
            Path.cwd() / filename,
            ROOT / filename,
        ]
    )
    return found if found is not None else config_dir() / filename


def find_config_file(filename: str = "config.ini") -> Path:
    found = _existing(
        [
            config_dir() / filename,
            Path.cwd() / filename,
            ROOT / filename,
        ]
    )
    return found if found is not None else config_dir() / filename


def log_file_path() -> Path:
    env = os.getenv("LOG_FILE")
    if env:
        return Path(env)
    return config_dir() / "myfans_downloader.log"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

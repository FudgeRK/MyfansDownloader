"""Load and save config.ini without destroying unrelated sections."""
from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Dict

from scripts.paths import downloads_dir, find_config_file, normalize_output_dir


def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    path = find_config_file()
    if path.is_file():
        config.read(path, encoding="utf-8")
    if not config.has_section("Settings"):
        config.add_section("Settings")
    if not config.has_option("Settings", "output_dir"):
        config.set("Settings", "output_dir", str(downloads_dir()))
    if not config.has_section("Filename"):
        config.add_section("Filename")
        config.set("Filename", "pattern", os.getenv("FILENAME_PATTERN", "{creator}_{date}_{id}"))
        config.set("Filename", "separator", os.getenv("FILENAME_SEPARATOR", "_"))
        config.set("Filename", "numbers", "")
        config.set("Filename", "letters", "")
    if not config.has_section("Threads"):
        config.add_section("Threads")
        config.set("Threads", "threads", os.getenv("THREAD_COUNT", "3"))
    return config


def save_config(config: configparser.ConfigParser) -> Path:
    path = find_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        config.write(handle)
    return path


def output_directory(config: configparser.ConfigParser) -> str:
    configured = config.get("Settings", "output_dir", fallback="downloads")
    env = os.getenv("DOWNLOADS_DIR")
    if env:
        return env
    return normalize_output_dir(configured)


def thread_count(config: configparser.ConfigParser) -> int:
    env = os.getenv("THREAD_COUNT")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    try:
        return max(1, config.getint("Threads", "threads", fallback=3))
    except ValueError:
        return 3


def segment_thread_count() -> int:
    try:
        return max(1, int(os.getenv("SEGMENT_DOWNLOAD_THREADS", "8")))
    except ValueError:
        return 8


def current_settings(config: configparser.ConfigParser) -> Dict[str, object]:
    return {
        "filename_pattern": os.getenv(
            "FILENAME_PATTERN", config.get("Filename", "pattern", fallback="{creator}_{date}_{id}")
        ),
        "filename_separator": os.getenv(
            "FILENAME_SEPARATOR", config.get("Filename", "separator", fallback="_")
        ),
        "auth_token": os.getenv("AUTH_TOKEN", config.get("Settings", "auth_token", fallback="")),
        "thread_count": thread_count(config),
        "write_metadata": os.getenv(
            "WRITE_METADATA", config.get("Settings", "write_metadata", fallback="0")
        ),
        "output_dir": output_directory(config),
    }

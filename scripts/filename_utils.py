"""Filename generation and optional gallery-dl style metadata."""
from __future__ import annotations

import json
import os
import re
from threading import Lock
from typing import Any, Dict, Optional

from scripts.utils import clean_filename, get_post_date

filename_lock = Lock()
generated_filenames = set()

DEFAULT_PATTERN = "{creator}_{date}_{id}"
DEFAULT_SEPARATOR = "_"


def read_filename_config(config) -> Dict[str, str]:
    try:
        return {
            "pattern": os.getenv(
                "FILENAME_PATTERN",
                config.get("Filename", "pattern", fallback=DEFAULT_PATTERN),
            ),
            "separator": os.getenv(
                "FILENAME_SEPARATOR",
                config.get("Filename", "separator", fallback=DEFAULT_SEPARATOR),
            ),
            "numbers": config.get("Filename", "numbers", fallback=""),
            "letters": config.get("Filename", "letters", fallback=""),
        }
    except Exception:
        return {
            "pattern": os.getenv("FILENAME_PATTERN", DEFAULT_PATTERN),
            "separator": os.getenv("FILENAME_SEPARATOR", DEFAULT_SEPARATOR),
            "numbers": "",
            "letters": "",
        }


def validate_filename_config(filename_config: Dict[str, str]) -> bool:
    pattern = filename_config.get("pattern") or ""
    allowed = ("{number}", "{date}", "{letter}", "{creator}", "{id}", "{title}")
    return any(token in pattern for token in allowed)


def _post_title(post: Dict[str, Any]) -> str:
    for key in ("title", "body", "content", "name"):
        value = post.get(key)
        if isinstance(value, str) and value.strip():
            first_line = value.strip().splitlines()[0].strip()
            if first_line:
                return first_line
    return str(post.get("id") or "untitled")[:8]


def generate_filename(
    post: Dict[str, Any],
    filename_config: Dict[str, str],
    output_folder: str,
    ext: str = ".mp4",
    max_length: int = 100,
    index: Optional[int] = None,
    unique: bool = False,
) -> str:
    pattern = filename_config.get("pattern") or DEFAULT_PATTERN
    separator = filename_config.get("separator") or DEFAULT_SEPARATOR
    username = (post.get("user") or {}).get("username") or "unknown"
    post_id = str(post.get("id") or "unknown")
    date_obj = get_post_date(post)
    post_date = date_obj.strftime("%Y-%m-%d") if date_obj else "unknown_date"
    title = clean_filename(_post_title(post), max_length=max_length)

    if ext and not ext.startswith("."):
        ext = "." + ext

    values = {
        "{creator}": username,
        "{date}": post_date,
        "{id}": post_id,
        "{title}": title,
        "{number}": str(filename_config.get("numbers") or ""),
        "{letter}": str(filename_config.get("letters") or ""),
        "{separator}": separator,
    }
    filename = pattern
    for token, value in values.items():
        filename = filename.replace(token, value)

    filename = re.sub(r"[\\/]+", separator, filename)
    filename = clean_filename(filename, max_length=max_length)
    if index is not None:
        filename = f"{filename}_{index}"
    if not filename.lower().endswith(ext.lower()):
        filename += ext

    candidate = filename
    if unique:
        base_name, file_ext = os.path.splitext(filename)
        counter = 1
        folder = output_folder or ""
        with filename_lock:
            while candidate in generated_filenames or (folder and os.path.exists(os.path.join(folder, candidate))):
                candidate = f"{base_name}_{counter}{file_ext}"
                counter += 1
            generated_filenames.add(candidate)
    return candidate


def generate_metadata(post: Dict[str, Any], filename: str, output_dir: str, ext: str = "mp4") -> None:
    enabled = str(os.getenv("WRITE_METADATA", "0")).strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return
    userdata = post.get("user") or {}
    date_obj = get_post_date(post)
    post_date = date_obj.strftime("%Y-%m-%d %H:%M:%S") if date_obj else None
    payload = {
        "service": "myfans",
        "category": "myfans",
        "subcategory": "myfans",
        "id": post.get("id", ""),
        "is_preview": False,
        "user": userdata.get("id", ""),
        "username": userdata.get("username", ""),
        "content": post.get("body", ""),
        "post_id": post.get("id", ""),
        "type": "attachment",
        "extension": str(ext).lstrip("."),
        "date": post_date,
        "post_date": post_date,
        "media_date": post_date,
    }
    metadata_path = os.path.join(output_dir, f"{filename}.json")
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    update_file_date(post, metadata_path)


def update_file_date(post: Dict[str, Any], full_path: str) -> None:
    date_obj = get_post_date(post)
    if date_obj is None or not os.path.exists(full_path):
        return
    try:
        timestamp = date_obj.timestamp()
        os.utime(full_path, (timestamp, timestamp))
    except (OSError, OverflowError, ValueError):
        return

"""Shared helpers for dates, filenames, URLs, and subprocesses."""
from __future__ import annotations

import datetime as dt
import logging
import os
import re
import shutil
import subprocess
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse

logger = logging.getLogger("myfans_downloader")

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

RESOLUTION_ORDER = ("uhd", "fhd", "hd", "sd", "ld")
RESOLUTION_HEIGHTS = {
    "uhd": 2160,
    "fhd": 1080,
    "hd": 720,
    "sd": 480,
    "ld": 360,
}
RESOLUTION_ALIASES = {
    "best": "best",
    "uhd": "uhd",
    "4k": "uhd",
    "2160": "uhd",
    "2160p": "uhd",
    "fhd": "fhd",
    "1080": "fhd",
    "1080p": "fhd",
    "fullhd": "fhd",
    "hd": "hd",
    "720": "hd",
    "720p": "hd",
    "sd": "sd",
    "480": "sd",
    "480p": "sd",
    "ld": "ld",
    "360": "ld",
    "360p": "ld",
}


def setup_logging() -> logging.Logger:
    log = logging.getLogger("myfans_downloader")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    log.addHandler(console)
    try:
        from scripts.paths import ensure_dir, log_file_path

        path = log_file_path()
        ensure_dir(path.parent)
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    except Exception as exc:
        log.warning("File logging disabled: %s", exc)
    log.propagate = False
    return log


def emit(progress_queue, message: str, level: str = "info") -> None:
    log = logging.getLogger("myfans_downloader")
    getattr(log, level, log.info)(message)
    if progress_queue is not None:
        progress_queue.put(message)


def url_dirname(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if "/" not in path:
        dir_path = "/"
    else:
        dir_path = path.rsplit("/", 1)[0] + "/"
    return urlunparse((parsed.scheme, parsed.netloc, dir_path, "", "", ""))


def is_absolute_url(url: str) -> bool:
    return url.lower().startswith(("http://", "https://"))


def join_url(base: str, url: str) -> str:
    if not url:
        raise ValueError("URL part is empty")
    if is_absolute_url(url):
        return url
    if not base:
        raise ValueError("Base URL is empty")
    if not base.endswith("/"):
        base = url_dirname(base)
    return urljoin(base, url)


def parse_iso_datetime(value: Any) -> Optional[dt.datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(value)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = text.replace(" ", "T", 1) if " " in text and "T" not in text else text
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return dt.datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
    return None


def get_post_date(post: Dict[str, Any]) -> Optional[dt.datetime]:
    for key in ("published_at", "publish_start_at", "posted_at", "created_at", "timestamp"):
        parsed = parse_iso_datetime(post.get(key))
        if parsed is not None:
            return parsed
    return None


def clean_filename(filename: str, max_length: int = 100) -> str:
    if filename is None:
        return "unnamed"
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in invalid else ch for ch in filename)
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return "unnamed"
    stem, ext = os.path.splitext(cleaned)
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    cleaned = stem + ext
    if len(cleaned) > max_length:
        stem, ext = os.path.splitext(cleaned)
        keep = max(1, max_length - len(ext))
        cleaned = stem[:keep] + ext
    return cleaned or "unnamed"


def normalize_resolution(value: Optional[str]) -> str:
    if not value:
        return "best"
    key = str(value).strip().lower().replace(" ", "")
    return RESOLUTION_ALIASES.get(key, key)


def height_for_resolution(value: str) -> Optional[int]:
    key = normalize_resolution(value)
    if key == "best":
        return None
    if key in RESOLUTION_HEIGHTS:
        return RESOLUTION_HEIGHTS[key]
    match = re.search(r"(\d{3,4})", key)
    if match:
        return int(match.group(1))
    return None


def variant_sort_key(item: Dict[str, Any]) -> tuple:
    height = item.get("height") or 0
    width = item.get("width") or 0
    size = item.get("size") or 0
    res = str(item.get("resolution") or "").lower()
    rank = RESOLUTION_ORDER.index(res) if res in RESOLUTION_ORDER else 99
    return (height, width, size, -rank)


def pick_video_variant(videos: Iterable[Dict[str, Any]], requested: str = "best") -> Optional[Dict[str, Any]]:
    usable = [v for v in videos if v and v.get("url")]
    if not usable:
        return None
    requested = normalize_resolution(requested)
    target_height = height_for_resolution(requested)
    if requested != "best":
        for video in usable:
            res = str(video.get("resolution") or "").lower()
            if res == requested or res == f"{target_height}p":
                return video
        if target_height:
            below = [
                v
                for v in usable
                if (v.get("height") or height_from_resolution_label(v.get("resolution")))
                and (v.get("height") or height_from_resolution_label(v.get("resolution"))) <= target_height
            ]
            if below:
                return sorted(below, key=variant_sort_key, reverse=True)[0]
    return sorted(usable, key=variant_sort_key, reverse=True)[0]


def height_from_resolution_label(label: Optional[str]) -> int:
    if not label:
        return 0
    text = str(label).lower()
    if text in RESOLUTION_HEIGHTS:
        return RESOLUTION_HEIGHTS[text]
    match = re.search(r"(\d{3,4})", text)
    return int(match.group(1)) if match else 0


def disk_has_space(path: str, required_bytes: int) -> bool:
    try:
        target = path if os.path.exists(path) else os.path.dirname(path) or "."
        return shutil.disk_usage(target).free >= required_bytes
    except Exception as exc:
        logger.error("Failed to check disk space: %s", exc)
        return False


def verify_video_file(file_path: str) -> bool:
    if not os.path.isfile(file_path) or os.path.getsize(file_path) <= 0:
        return False
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return os.path.getsize(file_path) > 1024
    except Exception as exc:
        logger.error("Error verifying video file %s: %s", file_path, exc)
        return False


def post_is_available(post: Dict[str, Any]) -> bool:
    if post.get("available") is False:
        return False
    if post.get("visible") is False and post.get("available") is not True:
        return False
    return True

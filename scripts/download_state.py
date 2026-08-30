"""Persistent download progress used by the web UI."""
from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.paths import config_dir, ensure_dir


class DownloadState:
    def __init__(self, state_dir: Optional[str] = None):
        directory = Path(state_dir) if state_dir else config_dir()
        ensure_dir(directory)
        self.state_file = str(directory / "download_state.json")
        self._lock = threading.RLock()
        self.state = self._load_state()
        completed = self.state.get("completed_files", [])
        self.state["completed_files"] = set(completed if isinstance(completed, list) else [])

    def _default_state(self) -> Dict[str, Any]:
        return {
            "downloads": {},
            "completed_files": [],
            "failed_files": {},
            "in_progress": {},
        }

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    merged = self._default_state()
                    merged.update(data)
                    return merged
            except (json.JSONDecodeError, OSError):
                return self._default_state()
        return self._default_state()

    def save_state(self) -> None:
        try:
            parent = os.path.dirname(self.state_file) or "."
            ensure_dir(Path(parent))
            with open(self.state_file, "w", encoding="utf-8") as handle:
                json.dump(self.get_serializable_state(), handle)
        except OSError as exc:
            print(f"Error saving state: {exc}")

    def add_download(self, post_id, status="pending", segments_total=0, segments_downloaded=0):
        with self._lock:
            self.state["downloads"][str(post_id)] = {
                "status": status,
                "start_time": datetime.now().isoformat(),
                "segments_total": segments_total,
                "segments_downloaded": segments_downloaded,
                "last_updated": datetime.now().isoformat(),
            }
            self.save_state()

    def update_progress(self, post_id, segments_downloaded):
        with self._lock:
            entry = self.state["downloads"].get(str(post_id))
            if not entry:
                return
            entry["segments_downloaded"] = segments_downloaded
            entry["last_updated"] = datetime.now().isoformat()
            self.save_state()

    def mark_completed(self, post_id):
        with self._lock:
            post_id = str(post_id)
            if post_id in self.state["downloads"]:
                self.state["downloads"][post_id]["status"] = "completed"
                self.state["downloads"][post_id]["last_updated"] = datetime.now().isoformat()
            self.state["completed_files"].add(post_id)
            self.save_state()

    def mark_failed(self, post_id, error):
        with self._lock:
            post_id = str(post_id)
            self.state["downloads"][post_id] = {
                "status": "failed",
                "error": str(error),
                "last_updated": datetime.now().isoformat(),
            }
            self.state["failed_files"][post_id] = str(error)
            self.save_state()

    def is_completed(self, post_id) -> bool:
        with self._lock:
            return str(post_id) in self.state["completed_files"]

    def get_progress(self, post_id) -> Dict[str, Any]:
        return self.state["downloads"].get(str(post_id), {})

    def is_file_exists(self, filename: str) -> bool:
        return filename in self.state["completed_files"]

    def get_serializable_state(self) -> Dict[str, Any]:
        with self._lock:
            completed = self.state.get("completed_files") or []
            if isinstance(completed, set):
                completed = list(completed)
            return {
                "downloads": copy.deepcopy(self.state.get("downloads") or {}),
                "completed_files": list(completed),
                "failed_files": copy.deepcopy(self.state.get("failed_files") or {}),
                "in_progress": copy.deepcopy(self.state.get("in_progress") or {}),
            }

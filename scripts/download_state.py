import json
import os
from datetime import datetime

class DownloadState:
    def __init__(self, state_dir="/config"):
        self.state_file = os.path.join(state_dir, "download_state.json")
        self.state = self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {
            "downloads": {},
            "completed_files": set(),
            "failed_files": {},
            "in_progress": {}
        }

    def save_state(self):
        with open(self.state_file, 'w') as f:
            # Convert set to list for JSON serialization
            state_copy = self.state.copy()
            state_copy["completed_files"] = list(self.state["completed_files"])
            json.dump(state_copy, f)

    def add_download(self, post_id, status="pending", segments_total=0, segments_downloaded=0):
        self.state["downloads"][post_id] = {
            "status": status,
            "start_time": datetime.now().isoformat(),
            "segments_total": segments_total,
            "segments_downloaded": segments_downloaded,
            "last_updated": datetime.now().isoformat()
        }
        self.save_state()

    def update_progress(self, post_id, segments_downloaded):
        if post_id in self.state["downloads"]:
            self.state["downloads"][post_id]["segments_downloaded"] = segments_downloaded
            self.state["downloads"][post_id]["last_updated"] = datetime.now().isoformat()
            self.save_state()

    def mark_completed(self, post_id):
        if post_id in self.state["downloads"]:
            self.state["downloads"][post_id]["status"] = "completed"
            self.state["completed_files"].add(post_id)
            self.save_state()

    def mark_failed(self, post_id, error):
        if post_id in self.state["downloads"]:
            self.state["downloads"][post_id]["status"] = "failed"
            self.state["failed_files"][post_id] = error
            self.save_state()

    def is_completed(self, post_id):
        return post_id in self.state["completed_files"]

    def get_progress(self, post_id):
        return self.state["downloads"].get(post_id, {})
import json
import os
from datetime import datetime

class DownloadState:
    def __init__(self, state_dir="/config"):
        self.state_file = os.path.join(state_dir, "download_state.json")
        self.state = self._load_state()
        # Convert completed_files list to set after loading
        self.state["completed_files"] = set(self.state.get("completed_files", []))
        self._scan_existing_files()

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # If file is corrupted, return default state
                return self._default_state()
        return self._default_state()

    def _default_state(self):
        return {
            "downloads": {},
            "completed_files": [],
            "failed_files": {},
            "in_progress": {}
        }

    def _scan_existing_files(self):
        """Scan existing files in downloads directory and add to completed files"""
        downloads_dir = os.getenv('DOWNLOADS_DIR', '/downloads')
        if os.path.exists(downloads_dir):
            for root, _, files in os.walk(downloads_dir):
                for file in files:
                    if file.endswith(('.mp4', '.jpg', '.png', '.gif')):
                        self.state["completed_files"].add(file)
        self.save_state()

    def save_state(self):
        """Save state to file, converting set to list for JSON serialization"""
        try:
            state_copy = self.get_serializable_state()
            with open(self.state_file, 'w') as f:
                json.dump(state_copy, f)
        except Exception as e:
            print(f"Error saving state: {e}")

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

    def is_file_exists(self, filename):
        """Check if file already exists in downloads"""
        return filename in self.state["completed_files"]

    def get_serializable_state(self):
        """Return a JSON-serializable version of the state"""
        state_copy = self.state.copy()
        if isinstance(state_copy.get("completed_files"), set):
            state_copy["completed_files"] = list(state_copy["completed_files"])
        return state_copy
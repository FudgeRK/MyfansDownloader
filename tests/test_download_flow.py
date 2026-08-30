from __future__ import annotations

import sys
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from MyfansDownloader_unified import _run_cli_entry
from scripts.utils import post_is_available


class StartDownloadDoneTests(unittest.TestCase):
    def test_start_download_always_emits_done(self):
        from scripts import myfans_dl

        queue = Queue()
        with patch.object(myfans_dl, "load_config", side_effect=RuntimeError("boom")):
            myfans_dl.start_download("user", "videos", "all", queue)
        items = []
        while not queue.empty():
            items.append(queue.get_nowait())
        self.assertIn("DONE", items)
        self.assertTrue(any("boom" in str(item) for item in items))

    def test_start_download_requires_username_for_bulk(self):
        from scripts import myfans_dl

        queue = Queue()
        fake_config = MagicMock()
        with patch.object(myfans_dl, "load_config", return_value=fake_config), patch.object(
            myfans_dl, "output_directory", return_value="downloads"
        ), patch.object(myfans_dl, "read_filename_config", return_value={"pattern": "{id}"}), patch.object(
            myfans_dl, "validate_filename_config", return_value=True
        ), patch.object(
            myfans_dl, "read_headers_from_file", return_value={"user-agent": "test"}
        ), patch.object(
            myfans_dl, "has_auth_token", return_value=False
        ), patch.object(
            myfans_dl, "thread_count", return_value=1
        ):
            myfans_dl.start_download("", "videos", "all", queue)
        items = []
        while not queue.empty():
            items.append(queue.get_nowait())
        self.assertEqual(items[-1], "DONE")
        self.assertTrue(any("username is required" in str(item).lower() for item in items))


class LauncherTests(unittest.TestCase):
    def test_cli_entry_swallows_system_exit(self):
        def boom():
            raise SystemExit(1)

        _run_cli_entry(boom)


class AccessLogicTests(unittest.TestCase):
    def test_old_subscribed_check_was_wrong(self):
        post = {"free": False, "id": "abc"}
        old_blocked = post.get("free") is False and not post.get("subscribed")
        self.assertTrue(old_blocked)
        self.assertTrue(post_is_available(post))


if __name__ == "__main__":
    unittest.main()

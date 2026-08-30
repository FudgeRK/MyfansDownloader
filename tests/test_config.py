from __future__ import annotations

import configparser
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.settings_loader import save_config


class ConfigPreserveTests(unittest.TestCase):
    def test_save_does_not_drop_sections(self):
        config = configparser.ConfigParser()
        config["Settings"] = {"output_dir": "downloads", "auth_token": ""}
        config["Filename"] = {"pattern": "{creator}_{date}_{id}", "separator": "_"}
        config["Threads"] = {"threads": "3"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            with patch("scripts.settings_loader.find_config_file", return_value=path):
                save_config(config)
                loaded = configparser.ConfigParser()
                loaded.read(path, encoding="utf-8")
            self.assertEqual(loaded.get("Settings", "output_dir"), "downloads")
            self.assertEqual(loaded.get("Filename", "pattern"), "{creator}_{date}_{id}")
            self.assertEqual(loaded.get("Threads", "threads"), "3")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helpers.deps import parse_requirement_name
from scripts.api import (
    collect_image_urls,
    media_headers,
    normalize_auth_token,
    parse_header_lines,
    videos_from_payload,
)
from scripts.filename_utils import generate_filename, generate_metadata, generated_filenames
from scripts.hls import pick_master_variant
from scripts.paths import normalize_output_dir
from scripts.utils import (
    clean_filename,
    join_url,
    parse_iso_datetime,
    pick_video_variant,
    post_is_available,
    url_dirname,
)


class RequirementParsingTests(unittest.TestCase):
    def test_strips_version_specifiers(self):
        self.assertEqual(parse_requirement_name("requests>=2.32.3"), "requests")
        self.assertEqual(parse_requirement_name("Flask>=3.1.0"), "Flask")
        self.assertEqual(parse_requirement_name("# comment"), "")
        self.assertEqual(parse_requirement_name("tqdm==4.67.1"), "tqdm")


class FilenameTests(unittest.TestCase):
    def setUp(self):
        generated_filenames.clear()

    def test_clean_reserved_and_invalid_chars(self):
        self.assertEqual(clean_filename('a<>:"/\\|?*b'), "a_________b")
        self.assertTrue(clean_filename("CON").startswith("_"))
        self.assertEqual(clean_filename(""), "unnamed")

    def test_generate_filename_placeholders(self):
        post = {
            "id": "abc-123",
            "published_at": "2024-01-02T03:04:05Z",
            "body": 'Hello "world"',
            "user": {"username": "creator"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            name = generate_filename(
                post,
                {"pattern": "{creator}_{date}_{id}", "separator": "_"},
                tmp,
            )
            self.assertEqual(name, "creator_2024-01-02_abc-123.mp4")

    def test_unique_when_file_exists(self):
        post = {"id": "1", "published_at": "2024-01-02T00:00:00Z", "user": {"username": "u"}}
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "u_2024-01-02_1.mp4"
            existing.write_bytes(b"x")
            name = generate_filename(
                post,
                {"pattern": "{creator}_{date}_{id}", "separator": "_"},
                tmp,
            )
            self.assertEqual(name, "u_2024-01-02_1_1.mp4")

    def test_metadata_json_escapes_content(self):
        post = {
            "id": "p1",
            "body": 'He said "hello"\nnew line',
            "user": {"id": "u1", "username": "name"},
            "published_at": "2024-01-02T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"WRITE_METADATA": "1"}):
            generate_metadata(post, "file.mp4", tmp, "mp4")
            payload = json.loads((Path(tmp) / "file.mp4.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["content"], 'He said "hello"\nnew line')
            self.assertEqual(payload["id"], "p1")


class DateAndUrlTests(unittest.TestCase):
    def test_parse_iso_z_suffix(self):
        parsed = parse_iso_datetime("2024-01-02T03:04:05Z")
        self.assertIsInstance(parsed, datetime)
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.day, 2)

    def test_url_dirname_does_not_use_os_path(self):
        self.assertEqual(
            url_dirname("https://cdn.example.com/a/b/file.m3u8"),
            "https://cdn.example.com/a/b/",
        )
        self.assertTrue(
            join_url("https://cdn.example.com/a/b/file.m3u8", "seg.ts").endswith("/a/b/seg.ts")
        )


class VideoSelectionTests(unittest.TestCase):
    def test_pick_requested_resolution_then_fallback(self):
        videos = [
            {"url": "u-720", "resolution": "hd", "height": 720},
            {"url": "u-1080", "resolution": "fhd", "height": 1080},
            {"url": "u-360", "resolution": "ld", "height": 360},
        ]
        self.assertEqual(pick_video_variant(videos, "1080p")["url"], "u-1080")
        self.assertEqual(pick_video_variant(videos, "best")["url"], "u-1080")
        self.assertEqual(pick_video_variant(videos, "480p")["url"], "u-360")

    def test_ignores_missing_urls(self):
        self.assertIsNone(pick_video_variant([{"resolution": "fhd"}], "best"))


class AccessCheckTests(unittest.TestCase):
    def test_missing_subscribed_field_does_not_block(self):
        self.assertTrue(post_is_available({"free": False, "id": "1"}))
        self.assertTrue(post_is_available({"free": False, "available": True}))
        self.assertFalse(post_is_available({"available": False}))


class HeaderTests(unittest.TestCase):
    def test_parse_skips_blank_and_comment_lines(self):
        parsed = parse_header_lines(
            "authorization: Token token=abc\n\n# comment\nuser-agent: test\nmalformed\n"
        )
        self.assertEqual(parsed["authorization"], "Token token=abc")
        self.assertEqual(parsed["user-agent"], "test")
        self.assertNotIn("malformed", parsed)

    def test_normalize_token_accepts_raw_cookie_value(self):
        self.assertEqual(normalize_auth_token("abc123"), "Token token=abc123")
        self.assertEqual(normalize_auth_token("Token token=abc123"), "Token token=abc123")
        self.assertEqual(normalize_auth_token(""), "")

    def test_media_headers_drop_authorization(self):
        headers = media_headers({"authorization": "Token token=secret", "user-agent": "ua"})
        self.assertNotIn("authorization", headers)
        self.assertEqual(headers["user-agent"], "ua")


class ImageUrlTests(unittest.TestCase):
    def test_collects_images_and_post_images(self):
        post = {
            "images": [{"url": "https://cdn/a.jpg"}],
            "post_images": [{"file_url": "https://cdn/b.jpg"}, {"file_url": "https://cdn/a.jpg"}],
        }
        self.assertEqual(
            collect_image_urls(post),
            ["https://cdn/a.jpg", "https://cdn/b.jpg"],
        )


class VideoPayloadTests(unittest.TestCase):
    def test_videos_from_main_and_trial(self):
        payload = {
            "main": [{"url": "https://cdn/main.m3u8", "resolution": "fhd", "height": 1080}],
            "trial": [{"url": "https://cdn/trial.m3u8", "resolution": "ld", "height": 360}],
        }
        videos = videos_from_payload(payload)
        self.assertEqual(len(videos), 2)
        self.assertEqual({item["source"] for item in videos}, {"main", "trial"})


class PathTests(unittest.TestCase):
    def test_docker_path_on_windows_maps_to_local_downloads(self):
        with patch("scripts.paths._is_docker", return_value=False), patch("os.name", "nt"):
            mapped = normalize_output_dir("/downloads")
            self.assertTrue(mapped.replace("\\", "/").endswith("downloads"))


class MasterPlaylistTests(unittest.TestCase):
    def test_picks_matching_or_lower_variant(self):
        import m3u8

        content = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
360p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
720p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
1080p.m3u8
"""
        playlist = m3u8.loads(content)
        chosen = pick_master_variant(playlist, 720)
        self.assertEqual(chosen.uri, "720p.m3u8")
        best = pick_master_variant(playlist, None)
        self.assertEqual(best.uri, "1080p.m3u8")


if __name__ == "__main__":
    unittest.main()

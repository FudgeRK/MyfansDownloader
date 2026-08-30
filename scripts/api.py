"""MyFans API client and header loading."""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.paths import find_header_file
from scripts.utils import height_from_resolution_label, pick_video_variant

logger = logging.getLogger("myfans_downloader")

API_BASE = "https://api.myfans.jp/api"
DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_thread_local = threading.local()


def parse_header_lines(text: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def normalize_auth_token(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    if token.lower().startswith("token token="):
        return token
    if token.lower().startswith("bearer "):
        return token
    return f"Token token={token}"


def read_headers_from_file(filename: str = "header.txt") -> Dict[str, str]:
    path = filename
    if not os.path.isabs(filename) and not os.path.isfile(filename):
        path = str(find_header_file(os.path.basename(filename)))
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Header file not found at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        headers = parse_header_lines(handle.read())

    env_token = os.getenv("AUTH_TOKEN", "").strip()
    if env_token and env_token != "your_token_here":
        headers["authorization"] = normalize_auth_token(env_token)

    if "authorization" in headers:
        headers["authorization"] = normalize_auth_token(headers["authorization"])

    headers.setdefault("user-agent", DEFAULT_USER_AGENT)
    headers.setdefault("accept", "application/json")
    headers.setdefault("x-mf-locale", "ja")
    headers.setdefault("origin", "https://myfans.jp")
    headers.setdefault("referer", "https://myfans.jp/")
    return headers


def media_headers(headers: Dict[str, str]) -> Dict[str, str]:
    keep = {}
    for key in ("user-agent", "referer", "origin", "accept"):
        if headers.get(key):
            keep[key] = headers[key]
    keep.setdefault("user-agent", DEFAULT_USER_AGENT)
    keep.setdefault("referer", "https://myfans.jp/")
    keep.setdefault("origin", "https://myfans.jp")
    keep["accept"] = "*/*"
    return keep


def has_auth_token(headers: Dict[str, str]) -> bool:
    value = headers.get("authorization", "")
    prefix = "Token token="
    if not value.lower().startswith(prefix.lower()):
        return bool(value)
    return bool(value[len(prefix) :].strip())


def write_auth_token(token: str, filename: str = "header.txt") -> None:
    path = str(find_header_file(filename))
    existing: Dict[str, str] = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            existing = parse_header_lines(handle.read())
    existing["authorization"] = normalize_auth_token(token)
    existing.setdefault("user-agent", DEFAULT_USER_AGENT)
    existing.setdefault("google-ga-data", "event328")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for key, value in existing.items():
            handle.write(f"{key}: {value}\n")


def make_session(headers: Optional[Dict[str, str]] = None, pool_size: int = 16) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if headers:
        session.headers.update(headers)
    return session


def thread_session(headers: Dict[str, str]) -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = make_session(headers)
        _thread_local.session = session
    return session


class MyFansClient:
    def __init__(self, headers: Optional[Dict[str, str]] = None, session: Optional[requests.Session] = None):
        self.headers = headers or read_headers_from_file()
        self.session = session or make_session(self.headers)

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
        response = self.session.get(url, headers=self.headers, params=params, timeout=timeout)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def get_user_by_username(self, username: str) -> Dict[str, Any]:
        url = f"{API_BASE}/v2/users/show_by_username"
        return self.get_json(url, params={"username": username})

    def get_post(self, post_id: str) -> Dict[str, Any]:
        return self.get_json(f"{API_BASE}/v2/posts/{post_id}")

    def get_post_videos(self, post_id: str) -> Dict[str, Any]:
        return self.get_json(f"{API_BASE}/v2/posts/{post_id}/videos")

    def get_user_plans(self, user_id: str) -> List[Dict[str, Any]]:
        data = self.get_json(f"{API_BASE}/v1/users/{user_id}/plans")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "plans"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _iter_paged(self, url: str, extra_params: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        page = 1
        seen_pages = set()
        params = dict(extra_params or {})
        params.setdefault("sort_key", "publish_start_at")
        params.setdefault("per_page", 20)
        while page and page not in seen_pages:
            seen_pages.add(page)
            params["page"] = page
            payload = self.get_json(url, params=params)
            items = _items_from_payload(payload)
            if not items:
                break
            for item in items:
                yield item
            pagination = payload.get("pagination") if isinstance(payload, dict) else None
            next_page = None
            if isinstance(pagination, dict):
                next_page = pagination.get("next") or pagination.get("next_page")
            if next_page in (None, "", False, page):
                if next_page == page:
                    break
                per_page = int(params.get("per_page") or 20)
                if not items or len(items) < per_page:
                    break
                page = page + 1
                continue
            try:
                page = int(next_page)
            except (TypeError, ValueError):
                break
            if page in seen_pages or len(seen_pages) > 10000:
                break

    def iter_user_posts(self, user_id: str) -> Iterator[Dict[str, Any]]:
        yield from self._iter_paged(f"{API_BASE}/v2/users/{user_id}/posts")

    def iter_back_number_posts(self, user_id: str) -> Iterator[Dict[str, Any]]:
        yield from self._iter_paged(f"{API_BASE}/v2/users/{user_id}/back_number_posts")

    def iter_plan_posts(self, plan_id: str, kind: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if kind:
            params["kind"] = kind
        yield from self._iter_paged(f"{API_BASE}/v2/plans/{plan_id}/posts", params)

    def iter_all_posts(self, user: Dict[str, Any], kind: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        user_id = user.get("id")
        if not user_id:
            return
        seen = set()
        sources = [self.iter_user_posts(user_id)]
        if user.get("current_back_number_plan"):
            sources.append(self.iter_back_number_posts(user_id))
        try:
            for plan in self.get_user_plans(user_id):
                plan_id = plan.get("id") if isinstance(plan, dict) else None
                if plan_id:
                    sources.append(self.iter_plan_posts(plan_id, kind=kind))
        except requests.RequestException as exc:
            logger.info("Could not list user plans: %s", exc)

        for source in sources:
            try:
                for post in source:
                    post_id = post.get("id")
                    if not post_id or post_id in seen:
                        continue
                    if kind and post.get("kind") and post.get("kind") != kind:
                        continue
                    seen.add(post_id)
                    yield post
            except requests.RequestException as exc:
                logger.warning("Failed while listing posts: %s", exc)


def _items_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("posts", "items", "results", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def collect_image_urls(post: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    seen = set()

    def add(url: Optional[str]) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        urls.append(url)

    for image in post.get("images") or []:
        if isinstance(image, dict):
            add(image.get("url") or image.get("file_url"))
    for image in post.get("post_images") or []:
        if isinstance(image, dict):
            add(image.get("file_url") or image.get("url"))
    single = post.get("post_image")
    if isinstance(single, dict):
        add(single.get("file_url") or single.get("url"))
    return urls


def videos_from_payload(payload: Any) -> List[Dict[str, Any]]:
    root = payload.get("data", payload) if isinstance(payload, dict) else payload
    videos: List[Dict[str, Any]] = []

    def push(source: str, items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            entry = dict(item)
            entry["source"] = source
            if not entry.get("height"):
                entry["height"] = height_from_resolution_label(entry.get("resolution"))
            videos.append(entry)

    if isinstance(root, list):
        push("main", root)
        return videos
    if not isinstance(root, dict):
        return videos
    push("main", root.get("main"))
    push("trial", root.get("trial"))
    push("main", root.get("videos"))
    push("main", root.get("items"))
    nested = root.get("videos")
    if isinstance(nested, dict):
        push("main", nested.get("main"))
        push("trial", nested.get("trial"))
    return videos


def get_video_info(
    post_id: str, session: requests.Session, headers: Dict[str, str]
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    client = MyFansClient(headers=headers, session=session)
    try:
        data = client.get_post(post_id)
    except requests.RequestException as exc:
        logger.error("API request failed for post %s: %s", post_id, exc)
        return None, None, str(exc)
    try:
        video_payload = client.get_post_videos(post_id)
    except requests.RequestException:
        video_payload = data.get("videos") if isinstance(data, dict) else None

    variants = videos_from_payload(video_payload)
    if not variants:
        variants = videos_from_payload(data.get("videos") if isinstance(data, dict) else None)
    resolution_info = resolution_info_from_variants(variants)
    if not resolution_info:
        return data, None, "No videos found"
    return data, resolution_info, None


def resolution_info_from_variants(variants: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    resolution_info: Dict[str, Dict[str, Any]] = {}
    for video in variants or []:
        source = video.get("source") or "main"
        if source == "trial":
            continue
        key = str(video.get("resolution") or video.get("height") or len(resolution_info))
        if key in resolution_info and resolution_info[key].get("source") != "trial":
            continue
        resolution_info[key] = {
            "url": video.get("url"),
            "size": video.get("size", 0),
            "duration": video.get("duration") or video.get("duration_ms", 0),
            "width": video.get("width", 0),
            "height": video.get("height") or height_from_resolution_label(video.get("resolution")),
            "source": source,
        }
    return resolution_info


def choose_video_url(resolution_info: Dict[str, Dict[str, Any]], requested: str = "best") -> Optional[Dict[str, Any]]:
    videos = []
    for key, info in resolution_info.items():
        item = dict(info)
        item.setdefault("resolution", key)
        videos.append(item)
    return pick_video_variant(videos, requested)

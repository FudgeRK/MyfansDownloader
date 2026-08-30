from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests
from tqdm import tqdm

from scripts.api import (
    MyFansClient,
    collect_image_urls,
    get_video_info,
    has_auth_token,
    media_headers,
    read_headers_from_file,
    videos_from_payload,
)
from scripts.filename_utils import (
    generate_filename,
    generate_metadata,
    read_filename_config,
    update_file_date,
    validate_filename_config,
)
from scripts.hls import download_stream
from scripts.settings_loader import load_config, output_directory, segment_thread_count, thread_count
from scripts.utils import (
    emit,
    height_for_resolution,
    normalize_resolution,
    pick_video_variant,
    post_is_available,
    setup_logging,
    verify_video_file,
)

logger = setup_logging()


def _extension_from_url(url: str, default: str = ".jpg") -> str:
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    if ext and len(ext) <= 5:
        return ext
    return default


def _filter_posts(posts: List[Dict[str, Any]], download_type: str) -> List[Dict[str, Any]]:
    if download_type == "free":
        return [post for post in posts if post.get("free")]
    if download_type in {"subscribed", "subscribe"}:
        return [post for post in posts if not post.get("free")]
    return posts


def _list_posts(client: MyFansClient, user: Dict[str, Any], kind: str) -> List[Dict[str, Any]]:
    posts = []
    for post in client.iter_all_posts(user, kind=kind):
        if post.get("kind") == kind or not post.get("kind"):
            posts.append(post)
    return posts


def download_image_bytes(session: requests.Session, url: str, headers: Dict[str, str], dest: str) -> bool:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    response = session.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    with open(dest, "wb") as handle:
        handle.write(response.content)
    return os.path.getsize(dest) > 0


def process_image_post(
    post_id: str,
    client: MyFansClient,
    output_dir: str,
    filename_config: Dict[str, str],
    progress_queue=None,
    download_state=None,
) -> bool:
    try:
        if download_state and download_state.is_completed(post_id):
            emit(progress_queue, f"Skipping already downloaded image post {post_id}")
            return True
        data = client.get_post(post_id)
        if not post_is_available(data):
            emit(progress_queue, f"No access to image post {post_id}", "error")
            if download_state:
                download_state.mark_failed(post_id, "no access")
            return False
        urls = collect_image_urls(data)
        if not urls:
            emit(progress_queue, f"No images found for post {post_id}", "error")
            if download_state:
                download_state.mark_failed(post_id, "no images")
            return False
        username = (data.get("user") or {}).get("username") or "unknown"
        folder = os.path.join(output_dir, username, "images")
        os.makedirs(folder, exist_ok=True)
        for idx, url in enumerate(urls):
            ext = _extension_from_url(url)
            index = idx + 1 if len(urls) > 1 else None
            filename = generate_filename(data, filename_config, folder, ext=ext, index=index)
            full_path = os.path.join(folder, filename)
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                update_file_date(data, full_path)
                generate_metadata(data, filename, folder, ext.lstrip("."))
                continue
            if not download_image_bytes(client.session, url, media_headers(client.headers), full_path):
                raise RuntimeError(f"Empty image download for {url}")
            update_file_date(data, full_path)
            generate_metadata(data, filename, folder, ext.lstrip("."))
            emit(progress_queue, f"Downloaded image: {filename}")
        if download_state:
            download_state.mark_completed(post_id)
        return True
    except Exception as exc:
        emit(progress_queue, f"Error downloading images for post {post_id}: {exc}", "error")
        if download_state:
            download_state.mark_failed(post_id, str(exc))
        return False


def handle_image_download(post_id, session, headers, output_dir, filename_config, progress_queue=None):
    client = MyFansClient(headers=headers, session=session)
    return process_image_post(post_id, client, output_dir, filename_config, progress_queue)


def process_video_post(
    post_id: str,
    client: MyFansClient,
    selected_resolution: str,
    output_dir: str,
    filename_config: Dict[str, str],
    progress_queue=None,
    download_state=None,
) -> bool:
    try:
        if download_state and download_state.is_completed(post_id):
            emit(progress_queue, f"Skipping already downloaded video post {post_id}")
            return True
        if download_state:
            download_state.add_download(post_id, status="in_progress")
        data = client.get_post(post_id)
        if not post_is_available(data):
            emit(progress_queue, f"No access to post {post_id}", "error")
            if download_state:
                download_state.mark_failed(post_id, "no access")
            return False
        try:
            video_payload = client.get_post_videos(post_id)
        except requests.RequestException:
            video_payload = data.get("videos")
        variants = videos_from_payload(video_payload) or videos_from_payload(data.get("videos"))
        main_variants = [item for item in variants if item.get("source") != "trial"]
        chosen = pick_video_variant(main_variants, selected_resolution)
        if not chosen:
            emit(progress_queue, f"No video URL for post {post_id} (locked or unavailable)", "error")
            if download_state:
                download_state.mark_failed(post_id, "no video url")
            return False

        username = (data.get("user") or {}).get("username") or "unknown"
        folder = os.path.join(output_dir, username, "videos")
        os.makedirs(folder, exist_ok=True)
        filename = generate_filename(data, filename_config, folder, ext=".mp4")
        full_path = os.path.join(folder, filename)

        if os.path.exists(full_path) and verify_video_file(full_path):
            generate_metadata(data, filename, folder)
            update_file_date(data, full_path)
            emit(progress_queue, f"File already exists and verified: {filename}")
            if download_state:
                download_state.mark_completed(post_id)
            return True
        if os.path.exists(full_path):
            emit(progress_queue, f"Corrupted file found, will redownload: {filename}", "warning")
            try:
                os.remove(full_path)
            except OSError:
                pass

        def on_progress(message: str) -> None:
            emit(progress_queue, message)

        success = download_stream(
            chosen["url"],
            full_path,
            media_headers(client.headers),
            post_id,
            requested_height=height_for_resolution(selected_resolution),
            progress=on_progress,
            segment_threads=segment_thread_count(),
        )
        if success:
            generate_metadata(data, filename, folder)
            update_file_date(data, full_path)
            emit(progress_queue, f"Successfully downloaded video: {filename}")
            if download_state:
                download_state.mark_completed(post_id)
            return True
        emit(progress_queue, f"Failed to download video for post {post_id}", "error")
        if download_state:
            download_state.mark_failed(post_id, "download failed")
        return False
    except Exception as exc:
        emit(progress_queue, f"Error processing post {post_id}: {exc}", "error")
        if download_state:
            download_state.mark_failed(post_id, str(exc))
        return False


def process_post_id(
    input_post_id,
    session,
    headers,
    selected_resolution,
    output_dir,
    filename_config,
    progress_bar=None,
    progress_queue=None,
):
    client = MyFansClient(headers=headers, session=session)
    try:
        return process_video_post(
            input_post_id,
            client,
            selected_resolution,
            output_dir,
            filename_config,
            progress_queue=progress_queue,
        )
    finally:
        if progress_bar:
            progress_bar.update(1)


def download_videos_concurrently(
    session,
    post_ids,
    selected_resolution,
    output_dir,
    filename_config,
    progress_queue=None,
    max_workers=1,
    download_state=None,
    headers=None,
):
    headers = headers or read_headers_from_file("header.txt")
    client = MyFansClient(headers=headers, session=session)
    total = len(post_ids)
    emit(progress_queue, f"Starting download of {total} video posts...")
    workers = max(1, int(max_workers or 1))
    progress_bar = tqdm(total=total, desc="Downloading videos", unit="video")
    if workers == 1:
        for post_id in post_ids:
            process_video_post(
                post_id,
                client,
                selected_resolution,
                output_dir,
                filename_config,
                progress_queue,
                download_state,
            )
            progress_bar.update(1)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def worker(post_id: str) -> None:
            thread_client = MyFansClient(headers=headers)
            process_video_post(
                post_id,
                thread_client,
                selected_resolution,
                output_dir,
                filename_config,
                progress_queue,
                download_state,
            )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker, post_id) for post_id in post_ids]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    emit(progress_queue, f"An error occurred during download: {exc}", "error")
                progress_bar.update(1)
    progress_bar.close()
    emit(progress_queue, "Download process completed")


def download_images_concurrently(
    session,
    post_ids,
    output_dir,
    filename_config,
    progress_queue=None,
    download_state=None,
    max_workers=1,
    headers=None,
):
    headers = headers or read_headers_from_file("header.txt")
    client = MyFansClient(headers=headers, session=session)
    total = len(post_ids)
    emit(progress_queue, f"Starting download of {total} image posts...")
    progress_bar = tqdm(total=total, desc="Downloading images", unit="post")
    workers = max(1, int(max_workers or 1))
    if workers == 1:
        for post_id in post_ids:
            process_image_post(post_id, client, output_dir, filename_config, progress_queue, download_state)
            progress_bar.update(1)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def worker(post_id: str) -> None:
            thread_client = MyFansClient(headers=headers)
            process_image_post(
                post_id, thread_client, output_dir, filename_config, progress_queue, download_state
            )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker, post_id) for post_id in post_ids]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    emit(progress_queue, f"An error occurred during download: {exc}", "error")
                progress_bar.update(1)
    progress_bar.close()
    emit(progress_queue, "Image download process completed")


def download_single_file(session, post_id, selected_resolution, output_dir, filename_config):
    headers = read_headers_from_file("header.txt")
    client = MyFansClient(headers=headers, session=session)
    process_video_post(post_id, client, selected_resolution, output_dir, filename_config)


def start_download(
    username,
    post_type,
    download_type,
    progress_queue,
    download_state=None,
    post_id=None,
    resolution="best",
):
    try:
        config = load_config()
        output_dir = output_directory(config)
        filename_config = read_filename_config(config)
        validate_filename_config(filename_config)
        headers = read_headers_from_file("header.txt")
        if not has_auth_token(headers):
            emit(
                progress_queue,
                "Warning: no authorization token set. Only free/public content will download.",
                "warning",
            )
        session = requests.Session()
        session.headers.update(headers)
        client = MyFansClient(headers=headers, session=session)
        workers = thread_count(config)
        resolution = normalize_resolution(resolution or "best")

        if post_id:
            emit(progress_queue, f"Starting download for post ID: {post_id}")
            if post_type == "images":
                process_image_post(
                    post_id, client, output_dir, filename_config, progress_queue, download_state
                )
            else:
                process_video_post(
                    post_id,
                    client,
                    resolution,
                    output_dir,
                    filename_config,
                    progress_queue,
                    download_state,
                )
            return

        if not username:
            emit(progress_queue, "Error: username is required for bulk downloads", "error")
            return

        emit(progress_queue, f"Starting download for user: {username}, type: {post_type}, mode: {download_type}")
        try:
            user = client.get_user_by_username(username)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (401, 403):
                emit(progress_queue, "API returned 401/403. Check the token in header.txt.", "error")
                return
            raise
        user_id = user.get("id")
        if not user_id:
            emit(progress_queue, "Failed to retrieve user ID. Check the username and token.", "error")
            return
        emit(progress_queue, f"Found user ID: {user_id}")

        kind = "image" if post_type == "images" else "video"
        emit(progress_queue, f"Fetching {kind} posts...")
        posts = _list_posts(client, user, kind)
        posts = _filter_posts(posts, download_type)
        emit(progress_queue, f"Total {kind} posts matched: {len(posts)}")
        post_ids = [post.get("id") for post in posts if post.get("id")]
        if not post_ids:
            emit(progress_queue, "No posts match the selected criteria.")
            return
        if kind == "video":
            download_videos_concurrently(
                session,
                post_ids,
                resolution,
                output_dir,
                filename_config,
                progress_queue,
                max_workers=workers,
                download_state=download_state,
                headers=headers,
            )
        else:
            download_images_concurrently(
                session,
                post_ids,
                output_dir,
                filename_config,
                progress_queue,
                download_state,
                max_workers=workers,
                headers=headers,
            )
    except Exception as exc:
        emit(progress_queue, f"Error: {exc}", "error")
    finally:
        if progress_queue is not None:
            progress_queue.put("DONE")


def _prompt_resolution() -> str:
    print("Select quality:")
    print("1. Best available")
    print("2. 2160p (4K)")
    print("3. 1080p")
    print("4. 720p")
    print("5. 480p")
    print("6. 360p")
    choice = input("Enter your choice (1-6, default 1): ").strip() or "1"
    return {
        "1": "best",
        "2": "uhd",
        "3": "fhd",
        "4": "hd",
        "5": "sd",
        "6": "ld",
    }.get(choice, "best")


def main() -> None:
    config = load_config()
    output_dir = output_directory(config)
    filename_config = read_filename_config(config)
    validate_filename_config(filename_config)
    try:
        headers = read_headers_from_file("header.txt")
    except FileNotFoundError as exc:
        print(exc)
        print("Create header.txt with: authorization: Token token=YOUR_TOKEN")
        sys.exit(1)
    if not has_auth_token(headers):
        print("Warning: authorization token is empty. Free content may still download.")

    session = requests.Session()
    session.headers.update(headers)
    client = MyFansClient(headers=headers, session=session)

    print("Select an option:")
    print("1. Download all video posts")
    print("2. Download a single video post by ID")
    print("3. List video post IDs")
    choice = input("Enter your choice (1/2/3): ").strip()

    if choice == "2":
        post_id = input("Enter the post ID to download: ").strip()
        if not post_id:
            print("Post ID is required.")
            return
        download_single_file(session, post_id, _prompt_resolution(), output_dir, filename_config)
        return
    if choice not in {"1", "3"}:
        print("Invalid choice.")
        return

    while True:
        name_creator = input("Enter a creator's username (without @) or type '0' to exit: ").strip()
        if name_creator == "0":
            return
        try:
            user = client.get_user_by_username(name_creator)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (401, 403):
                print("API returned 401/403. Check the token in header.txt.")
            else:
                print(f"An error occurred while connecting to the API: {exc}")
            continue
        except requests.RequestException as exc:
            print(f"An error occurred while connecting to the API: {exc}")
            continue
        if user.get("id"):
            break
        print("Failed to retrieve user ID. Please try again.")

    print("Fetching posts...")
    posts = _list_posts(client, user, "video")
    print(f"Total video posts found: {len(posts)}")
    print("Select which posts to download:")
    print("1. Free posts only")
    print("2. Subscribe posts only")
    print("3. All posts")
    save_choice = input("Enter your choice (1/2/3): ").strip()
    mapping = {"1": "free", "2": "subscribed", "3": "all"}
    filtered = _filter_posts(posts, mapping.get(save_choice, "all"))
    post_ids = [post.get("id") for post in filtered if post.get("id")]
    if not post_ids:
        print("No posts match the selected criteria.")
        return
    if choice == "3":
        print("\n".join(str(post_id) for post_id in post_ids))
        print(f"\n{len(post_ids)} post IDs")
        return
    download_videos_concurrently(
        session,
        post_ids,
        _prompt_resolution(),
        output_dir,
        filename_config,
        max_workers=thread_count(config),
        headers=headers,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

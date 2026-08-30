from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

from scripts.api import MyFansClient, has_auth_token, read_headers_from_file
from scripts.filename_utils import read_filename_config
from scripts.myfans_dl import download_images_concurrently
from scripts.settings_loader import load_config, output_directory, thread_count
from scripts.utils import setup_logging

logger = setup_logging()


def main() -> None:
    config = load_config()
    output_dir = output_directory(config)
    filename_config = read_filename_config(config)
    try:
        headers = read_headers_from_file("header.txt")
    except FileNotFoundError as exc:
        print(exc)
        sys.exit(1)
    if not has_auth_token(headers):
        print("Warning: authorization token is empty. Free content may still download.")

    name_creator = input("Enter a name creator (no require @): ").strip()
    if not name_creator:
        print("Username is required.")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(headers)
    client = MyFansClient(headers=headers, session=session)
    try:
        user = client.get_user_by_username(name_creator)
    except requests.RequestException as exc:
        print(f"Failed to retrieve user: {exc}")
        sys.exit(1)
    if not user.get("id"):
        print("Failed to retrieve user id from the API.")
        sys.exit(1)

    posts = [post for post in client.iter_all_posts(user, kind="image") if post.get("kind") == "image"]
    post_ids = [post.get("id") for post in posts if post.get("id")]
    if not post_ids:
        print("No image posts found.")
        return
    download_images_concurrently(
        session,
        post_ids,
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

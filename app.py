from flask import Flask, Response, jsonify, render_template, request
import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from queue import Empty, Queue

import requests

import scripts.myfans_dl as downloader
from scripts.api import has_auth_token, read_headers_from_file, write_auth_token
from scripts.download_state import DownloadState
from scripts.paths import ensure_dir, log_file_path
from scripts.settings_loader import current_settings, load_config, save_config

log_path = log_file_path()
ensure_dir(log_path.parent)
file_handler = RotatingFileHandler(log_path, maxBytes=10485760, backupCount=5, encoding="utf-8")
console_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

app = Flask(__name__)
progress_queue = Queue()
download_state = DownloadState()
download_lock = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/status")
def get_status():
    return jsonify(download_state.get_serializable_state())


@app.route("/download", methods=["POST"])
def start_download():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    post_type = data.get("type", "videos")
    download_type = data.get("download_type", "all")
    post_id = (data.get("post_id") or "").strip() or None
    resolution = data.get("resolution", "best")

    if not post_id and not username:
        return jsonify({"error": "username or post_id is required"}), 400
    if not download_lock.acquire(blocking=False):
        return jsonify({"error": "A download is already in progress"}), 409

    logger.info(
        "Starting download request - Username: %s, Type: %s, Mode: %s, PostID: %s, Resolution: %s",
        username,
        post_type,
        download_type,
        post_id,
        resolution,
    )

    def download_thread():
        try:
            downloader.start_download(
                username,
                post_type,
                download_type,
                progress_queue,
                download_state,
                post_id=post_id,
                resolution=resolution,
            )
        except Exception as exc:
            error = f"Error in download thread: {exc}"
            logger.exception(error)
            progress_queue.put(error)
            progress_queue.put("DONE")
        finally:
            download_lock.release()

    threading.Thread(target=download_thread, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/progress")
def progress():
    def generate():
        try:
            while True:
                try:
                    message = progress_queue.get(timeout=15)
                    text = str(message).replace("\r", " ").replace("\n", " ")
                    yield f"data: {text}\n\n"
                    if message == "DONE":
                        break
                except Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            return
        except Exception as exc:
            logger.error("Error in progress stream: %s", exc)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/test_post/<post_id>")
def test_post(post_id):
    try:
        session = requests.Session()
        headers = read_headers_from_file("header.txt")
        data, resolution_info, error = downloader.get_video_info(post_id, session, headers)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(
            {
                "post_type": "video"
                if data.get("videos")
                else "image"
                if data.get("images")
                else "unknown",
                "available": data.get("available", True),
                "is_free": data.get("free", False),
                "available_resolutions": list(resolution_info.keys()) if resolution_info else [],
                "title": data.get("title") or data.get("body", ""),
                "created_at": data.get("published_at") or data.get("created_at", ""),
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        return settings_api()
    return render_template("settings.html")


@app.route("/api/settings", methods=["GET", "POST"])
def settings_api():
    config = load_config()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if not config.has_section("Filename"):
            config.add_section("Filename")
        if not config.has_section("Threads"):
            config.add_section("Threads")
        if not config.has_section("Settings"):
            config.add_section("Settings")
        config.set("Filename", "pattern", str(data.get("filename_pattern") or "{creator}_{date}_{id}"))
        config.set("Filename", "separator", str(data.get("filename_separator") or "_"))
        try:
            threads = max(1, int(data.get("thread_count") or 3))
        except (TypeError, ValueError):
            threads = 3
        config.set("Threads", "threads", str(threads))
        if "write_metadata" in data:
            config.set("Settings", "write_metadata", "1" if data.get("write_metadata") else "0")
            os.environ["WRITE_METADATA"] = config.get("Settings", "write_metadata")
        token = data.get("auth_token")
        if token is not None:
            config.set("Settings", "auth_token", str(token))
            os.environ["AUTH_TOKEN"] = str(token)
            try:
                write_auth_token(str(token))
            except OSError as exc:
                logger.warning("Could not write header.txt: %s", exc)
        os.environ["FILENAME_PATTERN"] = config.get("Filename", "pattern")
        os.environ["FILENAME_SEPARATOR"] = config.get("Filename", "separator")
        os.environ["THREAD_COUNT"] = config.get("Threads", "threads")
        save_config(config)
        return jsonify({"status": "success"})

    settings = current_settings(config)
    try:
        headers = read_headers_from_file("header.txt")
        if has_auth_token(headers) and not settings.get("auth_token"):
            settings["auth_token"] = headers.get("authorization", "")
    except FileNotFoundError:
        pass
    return jsonify(settings)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

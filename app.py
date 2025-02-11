from flask import Flask, render_template, request, jsonify, Response
import scripts.myfans_dl as downloader
from scripts.download_state import DownloadState
from queue import Queue
import threading
import logging
import os
import requests
from logging.handlers import RotatingFileHandler

# Configure Flask logging
log_dir = os.getenv('CONFIG_DIR', '/config')
log_file = os.path.join(log_dir, 'myfans_downloader.log')

# Ensure log directory exists
os.makedirs(log_dir, exist_ok=True)

# Configure logging with both file and console handlers
file_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5)
console_handler = logging.StreamHandler()

# Set format for both handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
progress_queue = Queue()
download_state = DownloadState()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def get_status():
    return jsonify(download_state.get_serializable_state())

@app.route('/download', methods=['POST'])
def start_download():
    data = request.json
    username = data.get('username')
    post_type = data.get('type', 'videos')
    download_type = data.get('download_type', 'all')
    post_id = data.get('post_id')
    resolution = data.get('resolution', 'best')
    
    logger.info(f"Starting download request - Username: {username}, Type: {post_type}, Mode: {download_type}, PostID: {post_id}, Resolution: {resolution}")
    
    def download_thread():
        try:
            downloader.start_download(username, post_type, download_type, progress_queue, download_state, post_id=post_id, resolution=resolution)
        except Exception as e:
            error = f"Error in download thread: {str(e)}"
            logger.error(error)
            progress_queue.put(error)
    
    threading.Thread(target=download_thread).start()
    return jsonify({"status": "started"})

@app.route('/progress')
def progress():
    def generate():
        while True:
            progress = progress_queue.get()
            if progress == "DONE":
                break
            yield f"data: {progress}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/test_post/<post_id>')
def test_post(post_id):
    """Test endpoint to check post accessibility and available resolutions"""
    try:
        session = requests.Session()
        headers = downloader.read_headers_from_file("header.txt")
        data, resolution_info, error = downloader.get_video_info(post_id, session, headers)
        
        if error:
            return jsonify({"error": error}), 400
            
        return jsonify({
            "post_type": "video" if data.get('videos') else "image" if data.get('images') else "unknown",
            "is_free": data.get('free', False),
            "is_subscribed": data.get('subscribed', False),
            "available_resolutions": list(resolution_info.keys()) if resolution_info else [],
            "title": data.get('title', ''),
            "created_at": data.get('created_at', '')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
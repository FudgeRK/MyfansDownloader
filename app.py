from flask import Flask, render_template, request, jsonify, Response
import scripts.myfans_dl as downloader
from scripts.download_state import DownloadState
from queue import Queue, Empty  # Add both Queue and Empty
import threading
import logging
import os
import requests
from logging.handlers import RotatingFileHandler
import configparser

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
            try:
                progress = progress_queue.get(timeout=1)
                if progress == "DONE":
                    break
                yield f"data: {progress}\n\n"
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in progress stream: {e}")
                break
    
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

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.getenv('CONFIG_DIR', ''), 'config.ini')
    
    if request.method == 'POST':
        data = request.get_json()
        
        config['Settings'] = {
            'filename_pattern': data.get('filename_pattern', '{creator}_{date}_{title}'),
            'filename_separator': data.get('filename_separator', '_'),
            'auth_token': data.get('auth_token', ''),
            'thread_count': data.get('thread_count', '10')
        }
        
        # Save to config.ini
        with open(config_path, 'w') as f:
            config.write(f)
            
        # Update environment variables
        os.environ['FILENAME_PATTERN'] = data.get('filename_pattern', '{creator}_{date}_{title}')
        os.environ['FILENAME_SEPARATOR'] = data.get('filename_separator', '_')
        os.environ['AUTH_TOKEN'] = data.get('auth_token', '')
        os.environ['THREAD_COUNT'] = str(data.get('thread_count', 10))
        
        return jsonify({'status': 'success'})
        
    # GET request - return current settings
    try:
        config.read(config_path)
        settings = {
            'filename_pattern': os.getenv('FILENAME_PATTERN', config.get('Settings', 'filename_pattern', fallback='{creator}_{date}_{title}')),
            'filename_separator': os.getenv('FILENAME_SEPARATOR', config.get('Settings', 'filename_separator', fallback='_')),
            'auth_token': os.getenv('AUTH_TOKEN', config.get('Settings', 'auth_token', fallback='')),
            'thread_count': int(os.getenv('THREAD_COUNT', config.get('Settings', 'thread_count', fallback='10')))
        }
        return jsonify(settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
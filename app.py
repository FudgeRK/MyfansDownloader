from flask import Flask, render_template, request, jsonify, Response
import scripts.myfans_dl as downloader
from queue import Queue
import threading
import logging

# Configure Flask logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
progress_queue = Queue()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def start_download():
    data = request.json
    username = data.get('username')
    post_type = data.get('type', 'videos')  # 'videos' or 'images'
    download_type = data.get('download_type', 'all')  # 'all', 'free', or 'subscribed'
    post_id = data.get('post_id')
    
    logger.info(f"Starting download request - Username: {username}, Type: {post_type}, Mode: {download_type}, PostID: {post_id}")
    
    def download_thread():
        try:
            downloader.start_download(username, post_type, download_type, progress_queue, post_id=post_id)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
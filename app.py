from flask import Flask, render_template, request, jsonify, Response
import scripts.myfans_dl as downloader
from queue import Queue
import threading
import logging

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
    
    def download_thread():
        try:
            downloader.start_download(username, post_type, download_type, progress_queue)
        except Exception as e:
            progress_queue.put(f"Error: {str(e)}")
    
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
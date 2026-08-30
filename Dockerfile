FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONPATH="/app" \
    CONFIG_DIR=/config \
    DOWNLOADS_DIR=/downloads \
    FILENAME_PATTERN="{creator}_{date}_{id}" \
    FILENAME_SEPARATOR="_" \
    THREAD_COUNT="3" \
    AUTH_TOKEN="" \
    FLASK_APP=app.py \
    LOG_FILE="/config/myfans_downloader.log" \
    SEGMENT_DOWNLOAD_THREADS="8"

RUN mkdir -p /config /downloads

EXPOSE 5000

ENTRYPOINT ["/app/docker-entrypoint.sh"]

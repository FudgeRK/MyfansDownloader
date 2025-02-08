FROM python:3.12-slim

WORKDIR /app

# Install FFmpeg and other dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set default environment variables
ENV CONFIG_DIR=/config \
    DOWNLOADS_DIR=/downloads \
    FILENAME_PATTERN="{creator}_{date}" \
    FILENAME_SEPARATOR="_" \
    THREAD_COUNT="10"

# Create directories
RUN mkdir -p /config /downloads

# Create entrypoint script with environment variable handling
RUN echo '#!/bin/sh\n\
# Create or update config.ini with environment variables\n\
cat > /config/config.ini << EOF\n\
[Settings]\n\
output_dir = $DOWNLOADS_DIR\n\
\n\
[Filename]\n\
pattern = $FILENAME_PATTERN\n\
separator = $FILENAME_SEPARATOR\n\
numbers = 1234\n\
letters = FudgeRK\n\
\n\
[Threads]\n\
threads = $THREAD_COUNT\n\
EOF\n\
\n\
# Copy header.txt if it doesn'\''t exist\n\
if [ ! -f /config/header.txt ]; then\n\
    cp header.txt /config/\n\
fi\n\
\n\
python main.py' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
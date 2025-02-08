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

# Add the current directory to PYTHONPATH
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Set other environment variables
ENV CONFIG_DIR=/config \
    DOWNLOADS_DIR=/downloads \
    FILENAME_PATTERN="{creator}_{date}" \
    FILENAME_SEPARATOR="_" \
    THREAD_COUNT="10" \
    AUTH_TOKEN="" \
    FLASK_APP=app.py \
    FLASK_ENV=production

# Create directories
RUN mkdir -p /config /downloads

# Create entrypoint script
RUN echo '#!/bin/sh\n\
# Create config files from environment variables\n\
cat > /config/header.txt << EOF\n\
authorization: Token token=$AUTH_TOKEN\n\
google-ga-data: event328\n\
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36\n\
EOF\n\
\n\
python app.py' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/app/entrypoint.sh"]
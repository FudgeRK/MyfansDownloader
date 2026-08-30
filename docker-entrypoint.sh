#!/bin/sh
set -e

mkdir -p /config /downloads || true
if [ -n "$LOG_FILE" ]; then
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
  touch "$LOG_FILE" 2>/dev/null || true
fi

if [ ! -f /config/config.ini ] && [ -f /app/config.ini ]; then
  cp /app/config.ini /config/config.ini
fi

if [ -n "$AUTH_TOKEN" ] && [ "$AUTH_TOKEN" != "your_token_here" ]; then
  if [ ! -f /config/header.txt ]; then
    printf 'authorization: Token token=%s\nuser-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\ngoogle-ga-data: event328\n' "$AUTH_TOKEN" > /config/header.txt
  fi
fi

if [ ! -f /config/header.txt ]; then
  printf 'authorization: Token token=\nuser-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\ngoogle-ga-data: event328\n' > /config/header.txt
fi

exec python app.py

# MyFans Downloader

Download videos and images from [myfans.jp](https://myfans.jp) that your account can already access.

| Content | Support |
| --- | :---: |
| Videos 2160p / 1080p / 720p / 480p / 360p | Yes |
| Back-number videos | Yes |
| Images | Yes |
| Quality fallback if a requested resolution is missing | Yes |

## Requirements

- Python 3.9 or newer
- [FFmpeg](https://ffmpeg.org/) on your `PATH` (needed for videos)
- A MyFans account token for paid or members-only posts (optional for free/public posts)

On Windows you can run `SETUP.bat` once to install Python and dependencies, then `MyfansDownloader.bat` to start.

## Set your token

Paid and members-only posts need the `_mfans_token` cookie from myfans.jp after you sign in.

1. Open [myfans.jp](https://myfans.jp) and log in.
2. In browser DevTools, copy `_mfans_token`.
3. Put it in `header.txt` in the project folder (CLI) or in `config/header.txt` (Docker):

```
authorization: Token token=YOUR_TOKEN_HERE
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

You can paste either the raw cookie value or a full `Token token=...` line. Do not commit or share this file.

![Find the token in cookies](https://github.com/FudgeRK/MyfansVideoDownload/assets/30218389/d1beaf05-bdd7-4ee9-8799-fa7590fce79a)
![Authorization header format](https://github.com/FudgeRK/MyfansVideoDownload/assets/30218389/04357ec0-b076-4372-8dd1-31f2b9602901)

## Tutorial

[![Tutorial video](https://i.vimeocdn.com/video/1906551049-edd0aa942beaa0f83af9e3c04e3aba98d51253b81bf837967309ec1fb7cac618-d?mw=900&q=85)](https://vimeo.com/990745787)

## Python usage

From the project folder:

```bash
pip install -r requirements.txt
python main.py
```

`MyfansDownloader_unified.py` is the same menu with an extra CLI / web choice.

| Option | What it does |
| --- | --- |
| Download videos | All posts for a creator, a single post ID, or a list of IDs. Quality is selectable. |
| Download images | All image posts for a creator. |
| Web interface | Browser UI at http://127.0.0.1:5000 |

Downloads go to `downloads/<creator>/videos` or `downloads/<creator>/images` by default. Filenames and the output folder are set in `config.ini`.

## Docker usage

### Docker Compose

```bash
mkdir -p config downloads
# put header.txt in ./config
docker compose up
```

Open http://localhost:5000. Files are written to `./downloads`.

### Docker run

```bash
docker run -it \
  -e FILENAME_PATTERN="{creator}_{date}_{id}" \
  -e FILENAME_SEPARATOR="_" \
  -e THREAD_COUNT="3" \
  -v "$(pwd)/config:/config" \
  -v "$(pwd)/downloads:/downloads" \
  -p 5000:5000 \
  frequency2098/myfans-downloader:latest
```

## Configuration

| Setting | Where | Default |
| --- | --- | --- |
| Output folder | `config.ini` `[Settings] output_dir` or `DOWNLOADS_DIR` | `downloads` |
| Filename pattern | `config.ini` `[Filename] pattern` or `FILENAME_PATTERN` | `{creator}_{date}_{id}` |
| Filename separator | `config.ini` `[Filename] separator` or `FILENAME_SEPARATOR` | `_` |
| Post download threads | `config.ini` `[Threads] threads` or `THREAD_COUNT` | `3` |
| HLS segment threads | `SEGMENT_DOWNLOAD_THREADS` | `8` |
| JSON metadata | `WRITE_METADATA` (`1` / `0`) | `0` |
| Auth token | `header.txt` or `AUTH_TOKEN` | empty |

Filename placeholders: `{creator}`, `{date}`, `{id}`, `{title}`.

The web **Settings** page updates the token, filename pattern, and thread count without wiping the rest of `config.ini`.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Contributing

Bug reports and pull requests are welcome: [open a PR](https://github.com/FudgeRK/MyfansDownloader/pulls).

## Special thanks

[Shenggang](https://github.com/Shenggang), [bluems](https://github.com/bluems), [Serph91P](https://github.com/Serph91P), [albertphil](https://github.com/albertphil), [0xSho](https://github.com/mydcxiao), [Foxtopus](https://github.com/Foxtopus)

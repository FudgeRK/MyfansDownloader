import os
import sys
import time
import requests
import subprocess
import configparser
from tqdm import tqdm
from scripts.filename_utils import *
import concurrent.futures
import threading
import m3u8
from urllib.parse import urljoin
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def read_headers_from_file(filename):
    headers = {}
    config_dir = os.getenv('CONFIG_DIR', '')
    header_path = os.path.join(config_dir, filename)
    
    if not os.path.isfile(header_path):
        raise FileNotFoundError(f"Header file not found at {header_path}")
        
    with open(header_path, 'r') as file:
        for line in file:
            if ': ' in line:
                key, value = line.strip().split(': ', 1)
                headers[key.lower()] = value
    
    # Validate token presence
    if 'authorization' not in headers or not headers['authorization'].startswith('Token token='):
        raise ValueError("Invalid or missing authorization token in headers file")
        
    return headers

def get_posts_for_page(base_url, page, headers):
    url = base_url + str(page)
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    json_data = response.json()
    return json_data.get("data", [])

def verify_video_file(file_path):
    """Verify the integrity of downloaded video file"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", file_path, "-f", "null", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return result.returncode == 0
    except Exception:
        return False

def DL_File(m3u8_url_download, output_file, input_post_id, chunk_size=1024*1024, max_retries=3, retry_delay=5, progress_queue=None, download_state=None):
    """
    Parses the M3U8 playlist, downloads each TS segment individually, merges them into .ts,
    and converts to MP4 with FFmpeg.
    """
    try:
        # Check if file already exists and is complete
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            if verify_video_file(output_file):
                message = f"Verified existing file: {os.path.basename(output_file)}"
                logger.info(message)
                if progress_queue:
                    progress_queue.put(message)
                if download_state:
                    download_state.mark_completed(input_post_id)
                return True
            else:
                message = f"Corrupted file found, redownloading: {os.path.basename(output_file)}"
                logger.warning(message)
                if progress_queue:
                    progress_queue.put(message)
                os.remove(output_file)

        # Check for partial download
        temp_folder = output_file.replace('.mp4', '.ts_parts')
        if os.path.exists(temp_folder):
            message = f"Found partial download for {input_post_id}, resuming..."
            logger.info(message)
            if progress_queue:
                progress_queue.put(message)

        output_folder = os.path.dirname(output_file)
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        ts_file = output_file.replace('.mp4', '.ts')
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)

        for attempt in range(max_retries):
            try:
                message = f"Parsing M3U8 for post ID {input_post_id} (attempt {attempt+1}/{max_retries})..."
                if progress_queue:
                    progress_queue.put(message)
                    
                playlist = m3u8.load(m3u8_url_download)
                if not playlist.segments:
                    error = "No segments found in M3U8. Possible invalid URL or no access."
                    if progress_queue:
                        progress_queue.put(error)
                    return False

                message = f"Found {len(playlist.segments)} segment(s) for post ID {input_post_id}"
                if progress_queue:
                    progress_queue.put(message)
                    progress_queue.put("Downloading segments...")

                segment_files = []
                with tqdm(total=len(playlist.segments), desc=f"Segments for {input_post_id}", unit="seg") as seg_pbar:
                    if playlist.base_uri:
                        base_uri = playlist.base_uri
                    else:
                        if '/' in m3u8_url_download:
                            base_uri = m3u8_url_download.rsplit('/', 1)[0] + '/'
                        else:
                            base_uri = m3u8_url_download

                    if download_state:
                        download_state.add_download(input_post_id, segments_total=len(playlist.segments))

                    # Check completed segments in temp folder
                    existing_segments = []
                    if os.path.exists(temp_folder):
                        existing_segments = [f for f in os.listdir(temp_folder) if f.endswith('.ts')]
                        message = f"Found {len(existing_segments)} existing segments for {input_post_id}, checking integrity..."
                        logger.info(message)
                        if progress_queue:
                            progress_queue.put(message)

                    for i, segment in enumerate(playlist.segments):
                        if download_state:
                            download_state.update_progress(input_post_id, i)

                        segment_url = segment.uri
                        if not segment_uri_is_absolute(segment_url):
                            segment_url = urljoin(base_uri, segment_url)

                        seg_path = os.path.join(temp_folder, f"segment_{i}.ts")
                        
                        # Skip if segment exists and is valid
                        if f"segment_{i}.ts" in existing_segments:
                            if os.path.getsize(seg_path) > 0:
                                segment_files.append(seg_path)
                                seg_pbar.update(1)
                                continue

                        success_download = False

                        for seg_attempt in range(max_retries):
                            try:
                                with requests.get(segment_url, stream=True, timeout=120) as resp:
                                    resp.raise_for_status()
                                    with open(seg_path, "wb") as f:
                                        for chunk in resp.iter_content(chunk_size=chunk_size):
                                            if chunk:
                                                f.write(chunk)
                                success_download = True
                                time.sleep(0.25)
                                break
                            except Exception as e:
                                print(f"Error downloading segment {i} for post ID {input_post_id}: {e}")
                                if seg_attempt < max_retries - 1:
                                    print(f"Retrying segment {i} in {retry_delay} seconds...")
                                    time.sleep(retry_delay)

                        if not success_download:
                            print(f"Segment {i} still failed after retries. Aborting.")
                            return False

                        segment_files.append(seg_path)
                        seg_pbar.update(1)

                        if success_download:
                            if progress_queue and i % 10 == 0:  # Update progress every 10 segments
                                progress = (i + 1) / len(playlist.segments) * 100
                                progress_queue.put(f"Download progress: {progress:.1f}% ({i + 1}/{len(playlist.segments)})")

                with open(ts_file, 'wb') as outfile:
                    for seg_file in segment_files:
                        with open(seg_file, 'rb') as infile:
                            outfile.write(infile.read())

                if not os.path.exists(ts_file) or os.path.getsize(ts_file) == 0:
                    print("Merged TS file missing or empty. Aborting.")
                    return False

                try:
                    print(f"Converting merged TS to MP4 for post ID {input_post_id}...")
                    convert_result = subprocess.run(
                        ["ffmpeg", "-y", "-i", ts_file, "-c", "copy", output_file],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=600
                    )

                    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                        os.remove(ts_file)
                        for seg_file in segment_files:
                            os.remove(seg_file)
                        os.rmdir(temp_folder)
                        print(f"Successfully downloaded and converted post ID {input_post_id}.")
                        if download_state:
                            download_state.mark_completed(input_post_id)
                        return True

                except subprocess.TimeoutExpired:
                    print("FFmpeg conversion timed out.")
                except subprocess.CalledProcessError as e:
                    print(f"FFmpeg error during conversion: {e}")

            except Exception as e:
                print(f"Error processing M3U8 or merging segments for post ID {input_post_id}: {e}")

            if attempt < max_retries - 1:
                print(f"Retrying the entire M3U8 download process in {retry_delay} seconds...")
                time.sleep(retry_delay)

        print(f"Failed to process post ID {input_post_id} after {max_retries} overall attempts.")
        if download_state:
            download_state.mark_failed(input_post_id, "Conversion failed")
        return False

    except Exception as e:
        print(f"Unexpected error for post ID {input_post_id}: {e}")
        if download_state:
            download_state.mark_failed(input_post_id, str(e))
        return False

def segment_uri_is_absolute(uri: str) -> bool:
    return uri.lower().startswith(("http://", "https://"))

def process_post_id(input_post_id, session, headers, selected_resolution, output_dir, filename_config, progress_bar=None, progress_queue=None):
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            url = f"https://api.myfans.jp/api/v2/posts/{input_post_id}"
            response = session.get(url, headers=headers)
        
            if response.status_code == 401:
                error = "Authentication failed. Please check your token."
                logger.error(error)
                if progress_queue:
                    progress_queue.put(error)
                if progress_bar:
                    progress_bar.update(1)
                return
            elif response.status_code == 403:
                error = f"Access denied for post ID {input_post_id}. This might be a subscribed post."
                logger.error(error)
                if progress_queue:
                    progress_queue.put(error)
                if progress_bar:
                    progress_bar.update(1)
                return
                
            response.raise_for_status()
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                error = f"Network error on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s: {str(e)}"
                logger.warning(error)
                if progress_queue:
                    progress_queue.put(error)
                time.sleep(retry_delay)
                continue
            else:
                error = f"Final attempt failed for post {input_post_id}: {str(e)}"
                logger.error(error)
                if progress_queue:
                    progress_queue.put(error)
                return

    data = response.json()
    main_videos = data.get('videos', {}).get('main', [])
    name_creator = data['user']['username']

    if not main_videos:
        error = f"No videos found or you don't have access to this file for post ID {input_post_id}"
        if progress_queue:
            progress_queue.put(error)
        if progress_bar:
            progress_bar.update(1)
        return

    fhd_video = None
    sd_video = None
    for video in main_videos:
        if video["resolution"] == 'fhd':
            fhd_video = video
        elif video["resolution"] == 'sd':
            sd_video = video

    if fhd_video:
        selected_resolution = 'fhd'
        selected_video = fhd_video
    elif sd_video:
        selected_resolution = 'sd'
        selected_video = sd_video
    else:
        error = f"No suitable video resolution found for post ID {input_post_id}. Skipping."
        if progress_queue:
            progress_queue.put(error)
        if progress_bar:
            progress_bar.update(1)
        return

    video_url = selected_video["url"]
    video_base_url, video_extension = os.path.splitext(video_url)
    if selected_resolution == "fhd":
        target_resolution = "1080p"
    elif selected_resolution == "sd":
        target_resolution = "480p"

    m3u8_url = f"{video_base_url}/{target_resolution}.m3u8"
    m3u8_response = session.get(m3u8_url, headers=headers)

    if video_url and m3u8_response.status_code == 200 and target_resolution == "1080p":
        m3u8_url_download = f"{video_base_url}/1080p.m3u8"
    elif video_url and m3u8_response.status_code == 200 and target_resolution == "480p":
        m3u8_url_download = f"{video_base_url}/480p.m3u8"
    else:
        m3u8_url_download = f"{video_base_url}/360p.m3u8"

    output_folder = os.path.join(output_dir, name_creator, "videos")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    full_output_path = os.path.join(
        output_folder,
        generate_filename(data, filename_config, output_folder)
    )

    if video_url and m3u8_response.status_code == 200:
        message = f"Starting download of video {input_post_id}"
        if progress_queue:
            progress_queue.put(message)
            
        success = DL_File(m3u8_url_download, full_output_path, input_post_id, progress_queue=progress_queue)
        if not success:
            error = f"Failed to download post ID {input_post_id}"
            if progress_queue:
                progress_queue.put(error)
    else:
        error = f"No videos found or you don't have access to this file for post ID {input_post_id}"
        if progress_queue:
            progress_queue.put(error)

    if progress_bar:
        progress_bar.update(1)
def download_videos_concurrently(session, post_ids, selected_resolution, output_dir, filename_config, progress_queue=None, max_workers=1):
    headers = read_headers_from_file("header.txt")
    total_posts = len(post_ids)
    message = f"Starting download of {total_posts} posts one at a time..."
    if progress_queue:
        progress_queue.put(message)
    
    progress_bar = tqdm(total=total_posts, desc="Downloading videos", unit="video")

    def handle_download(input_post_id):
        try:
            process_post_id(
                input_post_id,
                session,
                headers,
                selected_resolution,
                output_dir,
                filename_config,
                progress_bar,
                progress_queue
            )
        except Exception as e:
            error = f"Error processing post {input_post_id}: {e}"
            if progress_queue:
                progress_queue.put(error)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = [executor.submit(handle_download, post_id) for post_id in post_ids]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                if progress_queue:
                    progress_queue.put(f"An error occurred during download: {e}")

    progress_bar.close()
    if progress_queue:
        progress_queue.put("Download process completed")

def download_single_file(session, post_id, selected_resolution, output_dir, filename_config):
    headers = read_headers_from_file("header.txt")
    try:
        response = session.get(f"https://api.myfans.jp/api/v2/posts/{post_id}", headers=headers)
        response.raise_for_status()
        process_post_id(post_id, session, headers, selected_resolution, output_dir, filename_config)
    except requests.RequestException as e:
        print(f"API request failed: {e}")

def check_disk_space(path, required_bytes):
    """Check if there's enough disk space available"""
    try:
        stat = os.statvfs(path)
        free_bytes = stat.f_frsize * stat.f_bavail
        return free_bytes >= required_bytes
    except Exception as e:
        logger.error(f"Failed to check disk space: {e}")
        return False

def start_download(username, post_type, download_type, progress_queue, download_state=None, post_id=None):
    """Handle downloads initiated from the web interface"""
    try:
        if post_id:
            # Single post download
            message = f"Starting download for post ID: {post_id}"
            logger.info(message)
            progress_queue.put(message)
            
            session = requests.Session()
            config_file_path = os.path.join(os.getenv('CONFIG_DIR', ''), 'config.ini')
            
            config = configparser.ConfigParser()
            config.read(config_file_path)
            
            output_dir = os.getenv('DOWNLOADS_DIR', config.get('Settings', 'output_dir'))
            filename_config = read_filename_config(config)
            
            if post_type == 'videos':
                selected_resolution = 'fhd'
                download_single_file(session, post_id, selected_resolution, output_dir, filename_config)
            else:  # images
                headers = read_headers_from_file("header.txt")
                handle_image_download(post_id, session, headers, output_dir, filename_config)
            progress_queue.put("DONE")
            return

        message = f"Starting download for user: {username}, type: {post_type}, mode: {download_type}"
        logger.info(message)
        progress_queue.put(message)
        
        session = requests.Session()
        config_file_path = os.path.join(os.getenv('CONFIG_DIR', ''), 'config.ini')
        
        if not os.path.isfile(config_file_path):
            error = "Error: config.ini not found"
            logger.error(error)
            progress_queue.put(error)
            return
            
        config = configparser.ConfigParser()
        config.read(config_file_path)
        
        # Get configuration
        output_dir = os.getenv('DOWNLOADS_DIR', config.get('Settings', 'output_dir'))
        filename_config = read_filename_config(config)
        
        # Set default resolution
        selected_resolution = 'fhd'

        # Process downloads based on type
        if post_type == 'videos':
            user_info_url = f"https://api.myfans.jp/api/v2/users/show_by_username?username={username}"
            message = f"Fetching user info from: {user_info_url}"
            logger.info(message)
            progress_queue.put(message)
            
            response = session.get(user_info_url, headers=read_headers_from_file("header.txt"))
            response.raise_for_status()
            user_data = response.json()
            
            message = f"Successfully retrieved user data for: {username}"
            logger.info(message)
            progress_queue.put(message)
            
            # Fetch posts
            back_number_plan = user_data.get('current_back_number_plan')
            user_id = user_data.get('id')
            
            if not user_id:
                error = "Failed to retrieve user ID. Please check the username and try again."
                logger.error(error)
                progress_queue.put(error)
                return
                
            message = f"Found user ID: {user_id}"
            logger.info(message)
            progress_queue.put(message)
            
            # Fetch regular posts
            base_url = f"https://api.myfans.jp/api/v2/users/{user_id}/posts?page="
            progress_queue.put("Fetching regular posts...")
            video_posts = []
            page = 1
            
            while True:
                try:
                    message = f"Fetching page {page} of regular posts..."
                    logger.info(message)
                    progress_queue.put(message)
                    
                    response = session.get(base_url + str(page), headers=read_headers_from_file("header.txt"))
                    response.raise_for_status()
                    json_data = response.json()
                    
                    if not json_data.get("data") or len(json_data["data"]) == 0:
                        message = "No more regular posts found"
                        logger.info(message)
                        progress_queue.put(message)
                        break
                        
                    current_page_videos = [post for post in json_data["data"] if post.get("kind") == "video"]
                    video_posts.extend(current_page_videos)
                    
                    message = f"Found {len(current_page_videos)} videos on page {page}"
                    logger.info(message)
                    progress_queue.put(message)
                    
                    page += 1
                    
                except requests.RequestException as e:
                    error = f"Error fetching page {page}: {e}"
                    logger.error(error)
                    progress_queue.put(error)
                    break

            # Fetch back number plan posts if available
            if back_number_plan:
                message = "Starting to fetch back number plan posts..."
                logger.info(message)
                progress_queue.put(message)
                
                back_plan_url = f"https://api.myfans.jp/api/v2/users/{user_id}/back_number_posts?page="
                page = 1
                
                while True:
                    try:
                        message = f"Fetching back plan page {page}..."
                        logger.info(message)
                        progress_queue.put(message)
                        
                        response = session.get(back_plan_url + str(page), headers=read_headers_from_file("header.txt"))
                        response.raise_for_status()
                        json_data = response.json()
                        
                        if not json_data.get("data") or len(json_data["data"]) == 0:
                            message = "No more back plan posts found"
                            logger.info(message)
                            progress_queue.put(message)
                            break
                            
                        current_page_videos = [post for post in json_data["data"] if post.get("kind") == "video"]
                        video_posts.extend(current_page_videos)
                        
                        message = f"Found {len(current_page_videos)} back plan videos on page {page}"
                        logger.info(message)
                        progress_queue.put(message)
                        
                        page += 1
                        
                    except requests.RequestException as e:
                        error = f"Error fetching back plan page {page}: {e}"
                        logger.error(error)
                        progress_queue.put(error)
                        break

            message = f"Total video posts found: {len(video_posts)}"
            logger.info(message)
            progress_queue.put(message)

            # Filter posts based on download_type
            if download_type == 'free':
                filtered_posts = [post for post in video_posts if post.get("free")]
            elif download_type == 'subscribed':
                filtered_posts = [post for post in video_posts if not post.get("free")]
            else:
                filtered_posts = video_posts

            # Check which files already exist
            existing_files = []
            missing_files = []
            
            for post in filtered_posts:
                post_id = post.get("id")
                filename = generate_filename(post, filename_config, output_dir)
                full_path = os.path.join(output_dir, post['user']['username'], "videos", filename)
                
                if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                    existing_files.append(post_id)
                    message = f"Skipping existing file: {filename}"
                    logger.info(message)
                    progress_queue.put(message)
                else:
                    missing_files.append(post_id)

            message = f"Found {len(existing_files)} existing files, {len(missing_files)} files to download"
            logger.info(message)
            progress_queue.put(message)

            # Estimate required space (rough estimate)
            estimated_size_per_video = 100 * 1024 * 1024  # 100MB per video
            required_space = len(missing_files) * estimated_size_per_video
            
            if not check_disk_space(output_dir, required_space):
                error = f"Not enough disk space. Need approximately {required_space//(1024*1024)}MB"
                logger.error(error)
                progress_queue.put(error)
                return

            if missing_files:
                message = f"Starting download of {len(missing_files)} missing files..."
                logger.info(message)
                progress_queue.put(message)
                download_videos_concurrently(session, missing_files, selected_resolution, output_dir, filename_config, progress_queue)
            else:
                message = "All files already downloaded!"
                logger.info(message)
                progress_queue.put(message)

            progress_queue.put("DONE")

        elif post_type == 'images':
            base_url = f"https://api.myfans.jp/api/v2/users/{user_id}/posts?page="
            progress_queue.put("Fetching image posts...")
            image_posts = []
            page = 1
            
            while True:
                try:
                    message = f"Fetching page {page} of image posts..."
                    logger.info(message)
                    progress_queue.put(message)
                    
                    response = session.get(base_url + str(page), headers=read_headers_from_file("header.txt"))
                    response.raise_for_status()
                    json_data = response.json()
                    
                    if not json_data.get("data"):
                        break
                        
                    current_page_images = [post for post in json_data["data"] if post.get("kind") == "image"]
                    image_posts.extend(current_page_images)
                    
                    message = f"Found {len(current_page_images)} images on page {page}"
                    logger.info(message)
                    progress_queue.put(message)
                    
                    page += 1
                    
                except requests.RequestException as e:
                    error = f"Error fetching page {page}: {e}"
                    logger.error(error)
                    progress_queue.put(error)
                    break

            # Filter posts based on download_type
            if download_type == 'free':
                filtered_posts = [post for post in image_posts if post.get("free")]
            elif download_type == 'subscribed':
                filtered_posts = [post for post in image_posts if not post.get("free")]
            else:
                filtered_posts = image_posts

            message = f"Starting download of {len(filtered_posts)} filtered image posts..."
            logger.info(message)
            progress_queue.put(message)

            post_ids = [post.get("id") for post in filtered_posts]
            download_images_concurrently(session, post_ids, output_dir, filename_config, progress_queue, download_state)

        progress_queue.put("DONE")
        
    except Exception as e:
        error = f"Error: {str(e)}"
        logger.error(error)
        progress_queue.put(error)
        raise

def download_images_concurrently(session, post_ids, output_dir, filename_config, progress_queue=None, download_state=None, max_workers=1):
    headers = read_headers_from_file("header.txt")
    total_posts = len(post_ids)
    message = f"Starting download of {total_posts} image posts one at a time..."
    if progress_queue:
        progress_queue.put(message)
    
    progress_bar = tqdm(total=total_posts, desc="Downloading images", unit="post")

    def handle_image_download(input_post_id):
        try:
            if download_state and download_state.is_completed(input_post_id):
                message = f"Skipping already downloaded image post ID {input_post_id}"
                logger.info(message)
                if progress_queue:
                    progress_queue.put(message)
                progress_bar.update(1)
                return

            url = f"https://api.myfans.jp/api/v2/posts/{input_post_id}"
            response = session.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            images = data.get('images', {}).get('main', [])
            if not images:
                error = f"No images found for post ID {input_post_id}"
                logger.error(error)
                if progress_queue:
                    progress_queue.put(error)
                if download_state:
                    download_state.mark_failed(input_post_id, error)
                progress_bar.update(1)
                return

            name_creator = data['user']['username']
            output_folder = os.path.join(output_dir, name_creator, "images")
            os.makedirs(output_folder, exist_ok=True)

            for idx, image in enumerate(images):
                image_url = image.get('url')
                if not image_url:
                    continue

                file_name = generate_filename(data, filename_config, output_folder)
                if len(images) > 1:
                    base, ext = os.path.splitext(file_name)
                    file_name = f"{base}_{idx + 1}{ext}"

                full_path = os.path.join(output_folder, file_name)
                
                if os.path.exists(full_path):
                    message = f"Image already exists: {file_name}"
                    logger.info(message)
                    if progress_queue:
                        progress_queue.put(message)
                    continue

                img_response = session.get(image_url, headers=headers)
                img_response.raise_for_status()

                with open(full_path, 'wb') as f:
                    f.write(img_response.content)

                message = f"Downloaded image: {file_name}"
                logger.info(message)
                if progress_queue:
                    progress_queue.put(message)

            if download_state:
                download_state.mark_completed(input_post_id)
            progress_bar.update(1)

        except Exception as e:
            error = f"Error downloading images for post {input_post_id}: {str(e)}"
            logger.error(error)
            if progress_queue:
                progress_queue.put(error)
            if download_state:
                download_state.mark_failed(input_post_id, str(e))
            progress_bar.update(1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(handle_image_download, post_id) for post_id in post_ids]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                if progress_queue:
                    progress_queue.put(f"An error occurred during download: {e}")

    progress_bar.close()
    if progress_queue:
        progress_queue.put("Image download process completed")

class DownloadState:
    def __init__(self, state_dir="/config"):
        self.state_file = os.path.join(state_dir, "download_state.json")
        self.state = self._load_state()
        self._cleanup_incomplete()

    def _cleanup_incomplete(self):
        """Check for incomplete downloads and mark them for retry"""
        downloads_dir = os.getenv('DOWNLOADS_DIR', '/downloads')
        for post_id, info in self.state["downloads"].items():
            if info["status"] == "in_progress":
                # Check if the download was interrupted
                temp_folder = os.path.join(downloads_dir, f"{post_id}_parts")
                if os.path.exists(temp_folder):
                    self.state["downloads"][post_id]["status"] = "incomplete"
                    self.state["downloads"][post_id]["segments_downloaded"] = len(
                        [f for f in os.listdir(temp_folder) if f.endswith('.ts')]
                    )
        self.save_state()

def main():
    session = requests.Session()
    config_file_path = 'config.ini'

    if os.path.isfile(config_file_path):
        config = configparser.ConfigParser()
        config.read(config_file_path)
        try:
            output_dir = config.get('Settings', 'output_dir')
        except (configparser.NoSectionError, configparser.NoOptionError):
            print("Error: 'output_dir' not found in [Settings] section of config.ini.")
            sys.exit(1)

        try:
            max_workers = config.getint('Threads', 'threads')
            if max_workers < 1:
                print("Error: 'threads' must be a positive integer. Using default value 10.")
                max_workers = 10
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            print("Warning: 'threads' not found or invalid in [Threads] section. Using default value 10.")
            max_workers = 10

    else:
        output_dir = input("Enter the output directory: ")
        if output_dir == '0':
            return
        config = configparser.ConfigParser()
        config['Settings'] = {'output_dir': output_dir}
        config['Filename'] = {
            'pattern': '{creator}_{date}',
            'separator': '_',
            'numbers': '1234',
            'letters': 'FudgeRK'
        }
        config['Threads'] = {'threads': '10'}
        with open(config_file_path, 'w') as configfile:
            config.write(configfile)
        print(f"Created default config.ini with pattern '{config['Filename']['pattern']}' and threads=10.")
        max_workers = 10

    filename_config = read_filename_config(config)
    validate_filename_config(filename_config)

    while True:
        name_creator = input("Enter a creator's username (without @) or type '0' to exit: ")
        if name_creator.lower() == '0':
            sys.exit()
        new_base_url = f"https://api.myfans.jp/api/v2/users/show_by_username?username={name_creator}"
        headers = read_headers_from_file("header.txt")
        try:
            response = requests.get(new_base_url, headers=headers)
            response.raise_for_status()
            new_json_data = response.json()
            user_id = new_json_data.get("id")
            if user_id:
                break
            else:
                print("Failed to retrieve user ID from the API endpoint. Please try again.")
        except requests.RequestException as e:
            print(f"An error occurred while connecting to the API: {e}")

    print("Select an option:")
    print("1. Download all video posts")
    print("2. Download a single video post by ID")
    choice = input("Enter your choice (1/2): ")

    if choice == '1':
        # First get back number plan info
        user_info_url = f"https://api.myfans.jp/api/v2/users/show_by_username?username={name_creator}"  # Changed URL format
        print("Fetching user info and plans...")
        try:
            response = session.get(user_info_url, headers=headers)
            response.raise_for_status()
            user_data = response.json()
            back_number_plan = user_data.get('current_back_number_plan')
            user_id = user_data.get('id')  # Get user_id from the response
            
            if not user_id:
                print("Failed to retrieve user ID. Please check the username and try again.")
                return
            
            # Fetch regular posts
            base_url = f"https://api.myfans.jp/api/v2/users/{user_id}/posts?page="
            print("Fetching regular posts...")
            video_posts = []
            page = 1
            
            with tqdm(desc="Fetching regular posts") as pbar:
                while True:
                    try:
                        response = requests.get(base_url + str(page), headers=headers)
                        response.raise_for_status()
                        json_data = response.json()
                        
                        if not json_data.get("data"):
                            break
                            
                        for post in json_data["data"]:
                            if post.get("kind") == "video":
                                video_posts.append(post)
                        
                        page += 1
                        pbar.update(1)
                        
                    except requests.RequestException as e:
                        print(f"\nError fetching page {page}: {e}")
                        break
            
            # Fetch back number plan posts if available
            if back_number_plan:
                print("\nFetching back number plan posts...")
                back_plan_url = f"https://api.myfans.jp/api/v2/users/{user_id}/back_number_posts?page="
                page = 1
                
                with tqdm(desc="Fetching back plan posts") as pbar:
                    while True:
                        try:
                            response = requests.get(back_plan_url + str(page), headers=headers)
                            response.raise_for_status()
                            json_data = response.json()
                            
                            if not json_data.get("data"):
                                break
                                
                            for post in json_data["data"]:
                                if post.get("kind") == "video":
                                    video_posts.append(post)
                            
                            page += 1
                            pbar.update(1)
                            
                        except requests.RequestException as e:
                            print(f"\nError fetching back plan page {page}: {e}")
                            break
            
            print(f"\nTotal video posts found: {len(video_posts)}")

            print("Select which posts to download:")
            print("1. Free posts only")
            print("2. Subscribe posts only")
            print("3. All posts")
            save_choice = input("Enter your choice (1/2/3): ").strip()

            if save_choice == "1":
                post_ids = [post.get("id") for post in video_posts if post.get("free")]
            elif save_choice == "2":
                post_ids = [post.get("id") for post in video_posts if not post.get("free")]
            else:
                post_ids = [post.get("id") for post in video_posts]

            if not post_ids:
                print("No posts match the selected criteria.")
                return

            selected_resolution = 'fhd'
            download_videos_concurrently(session, post_ids, selected_resolution, output_dir, filename_config)

        except requests.RequestException as e:
            print(f"An error occurred while fetching posts: {e}")

    elif choice == '2':
        post_id = input("Enter the post ID to download: ")
        selected_resolution = 'fhd'
        download_single_file(session, post_id, selected_resolution, output_dir, filename_config)

    else:
        print("Invalid choice.")
        return

if __name__ == "__main__":
    main()

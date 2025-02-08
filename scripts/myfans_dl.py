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
    with open(filename, 'r') as file:
        for line in file:
            if ': ' in line:
                key, value = line.strip().split(': ', 1)
                headers[key.lower()] = value
    return headers

def get_posts_for_page(base_url, page, headers):
    url = base_url + str(page)
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    json_data = response.json()
    return json_data.get("data", [])

def DL_File(m3u8_url_download, output_file, input_post_id, chunk_size=1024*1024, max_retries=3, retry_delay=5):
    """
    Parses the M3U8 playlist, downloads each TS segment individually, merges them into .ts,
    and converts to MP4 with FFmpeg.
    """
    try:
        output_folder = os.path.dirname(output_file)
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        ts_file = output_file.replace('.mp4', '.ts')
        temp_folder = ts_file + "_parts"
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)

        for attempt in range(max_retries):
            try:
                print(f"Parsing M3U8 for post ID {input_post_id} (attempt {attempt+1}/{max_retries})...")
                playlist = m3u8.load(m3u8_url_download)
                if not playlist.segments:
                    print("No segments found in M3U8. Possible invalid URL or no access.")
                    return False

                print(f"Found {len(playlist.segments)} segment(s) for post ID {input_post_id}.")
                print("Downloading individually...")

                segment_files = []
                with tqdm(total=len(playlist.segments), desc="Segments", unit="seg") as seg_pbar:
                    if playlist.base_uri:
                        base_uri = playlist.base_uri
                    else:
                        if '/' in m3u8_url_download:
                            base_uri = m3u8_url_download.rsplit('/', 1)[0] + '/'
                        else:
                            base_uri = m3u8_url_download

                    for i, segment in enumerate(playlist.segments):
                        segment_url = segment.uri
                        if not segment_uri_is_absolute(segment_url):
                            segment_url = urljoin(base_uri, segment_url)

                        seg_path = os.path.join(temp_folder, f"segment_{i}.ts")
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
        return False

    except Exception as e:
        print(f"Unexpected error for post ID {input_post_id}: {e}")
        return False

def segment_uri_is_absolute(uri: str) -> bool:
    return uri.lower().startswith(("http://", "https://"))

def process_post_id(input_post_id, session, headers, selected_resolution, output_dir, filename_config, progress_bar=None):
    url = f"https://api.myfans.jp/api/v2/posts/{input_post_id}"
    try:
        response = session.get(url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Request failed for post ID {input_post_id}: {e}")
        if progress_bar:
            progress_bar.update(1)
        return

    data = response.json()
    main_videos = data['videos']['main']
    name_creator = data['user']['username']

    if main_videos:
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
            print(f"No suitable video resolution found for post ID {input_post_id}. Skipping.")
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
        
        success = DL_File(m3u8_url_download, full_output_path, input_post_id)
        if not success:
            print(f"Failed to download post ID {input_post_id}.")
            pass
    else:
        print(f"No videos found or you don't have access to this file for post ID {input_post_id}.")

    if progress_bar:
        progress_bar.update(1)

def download_videos_concurrently(session, post_ids, selected_resolution, output_dir, filename_config, max_workers=1):  # Changed to 1
    """Download videos one at a time to avoid conflicts"""
    headers = read_headers_from_file("header.txt")
    total_posts = len(post_ids)
    print(f"\nStarting download of {total_posts} posts one at a time...")
    
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
                progress_bar
            )
        except Exception as e:
            print(f"\nError processing post {input_post_id}: {e}")

    # Use ThreadPoolExecutor with max_workers=1 to process one video at a time
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = [executor.submit(handle_download, post_id) for post_id in post_ids]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"\nAn error occurred during download: {e}")

    progress_bar.close()
    print("\nDownload process completed.")

def download_single_file(session, post_id, selected_resolution, output_dir, filename_config):
    headers = read_headers_from_file("header.txt")
    try:
        response = session.get(f"https://api.myfans.jp/api/v2/posts/{post_id}", headers=headers)
        response.raise_for_status()
        process_post_id(post_id, session, headers, selected_resolution, output_dir, filename_config)
    except requests.RequestException as e:
        print(f"API request failed: {e}")

def start_download(username, post_type, download_type, progress_queue):
    """Handle downloads initiated from the web interface"""
    try:
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
                    
                    if not json_data.get("data"):
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
            
            # ... rest of the download logic with similar logging ...
            
        progress_queue.put("DONE")
        
    except Exception as e:
        error = f"Error: {str(e)}"
        logger.error(error)
        progress_queue.put(error)
        raise

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
``` 

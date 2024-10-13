import os
import sys
import time
import requests
import subprocess
import configparser
from tqdm import tqdm
from filename_utils import *
import concurrent.futures
import threading

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

def DL_File(m3u8_url_download, output_file, input_post_id):
    try:
        output_folder = os.path.dirname(output_file)
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        result = subprocess.run(
            ["ffmpeg", "-n", "-i", m3u8_url_download, "-c:v", "copy", "-c:a", "copy", "-loglevel", "quiet", output_file],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30  
        )

        return True

    except subprocess.TimeoutExpired:
        print(f"FFmpeg timed out for post ID {input_post_id}.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error while downloading and converting .m3u8 to .mp4 for post ID {input_post_id}: {e}")
        print(f"FFmpeg stderr: {e.stderr.decode('utf-8')}")
        return False
    except Exception as e:
        print(f"Unexpected error for post ID {input_post_id}: {e}")
        return False


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

        full_output_path = os.path.join(output_folder, generate_filename(data, filename_config, output_folder))
        
        success = DL_File(m3u8_url_download, full_output_path, input_post_id)
        if not success:
            print(f"Failed to download post ID {input_post_id}.")
            pass
    else:
        print(f"No videos found or you don't have access to this file for post ID {input_post_id}.")

    if progress_bar:
        progress_bar.update(1)

def download_videos_concurrently(session, post_ids, selected_resolution, output_dir, filename_config, max_workers=10):
    headers = read_headers_from_file("header.txt")

    progress_bar = tqdm(total=len(post_ids), desc="Downloading videos", unit="video")

    def handle_download(input_post_id):
        process_post_id(input_post_id, session, headers, selected_resolution, output_dir, filename_config, progress_bar)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(handle_download, post_id) for post_id in post_ids]

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"An error occurred during download: {e}")

    progress_bar.close()
    print("\nDownload process completed.")

def download_single_file(session, post_id, selected_resolution, output_dir, filename_config):
    headers = read_headers_from_file("header.txt")
    process_post_id(post_id, session, headers, selected_resolution, output_dir, filename_config)

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
        base_url = f"https://api.myfans.jp/api/v2/users/{user_id}/posts?sort_key=publish_start_at&page="

        print("Fetching posts and collecting video posts...")
        video_posts = []
        page = 1
        headers = read_headers_from_file("header.txt")

        with tqdm(desc="Fetching pages") as pbar:
            while True:
                try:
                    page_data = get_posts_for_page(base_url, page, headers)
                    if not page_data:
                        break
                    page += 1

                    for post in page_data:
                        if post.get("kind") == "video":
                            video_posts.append(post)
                    pbar.update(1)
                except requests.HTTPError as e:
                    print(f"Error fetching posts: {e}")
                    break
                except requests.RequestException as e:
                    print(f"Request failed: {e}")
                    break

        if not video_posts:
            print("No video posts found.")
            return

        video_count = len(video_posts)

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

    elif choice == '2':
        post_id = input("Enter the post ID to download: ")
        selected_resolution = 'fhd'
        download_single_file(session, post_id, selected_resolution, output_dir, filename_config)

    else:
        print("Invalid choice.")
        return

if __name__ == "__main__":
    main()

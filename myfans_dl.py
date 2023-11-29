import os
import sys
import time
import random
import string
import datetime
import requests
import subprocess
import configparser
import concurrent.futures

# Function to read headers from a file
def read_headers_from_file(filename):
    headers = {}
    with open(filename, 'r') as file:
        for line in file:
            key, value = line.strip().split(': ')
            headers[key.lower()] = value
    return headers

# Function to remove a line with a specified ID from the input file
def remove_line_with_id(input_file_path, post_id):
    with open(input_file_path, 'r') as file:
        lines = file.readlines()
    with open(input_file_path, 'w') as file:
        for line in lines:
            if line.strip() != post_id:
                file.write(line)

# Function to download and convert the .m3u8 playlist to .mp4 using FFmpeg
def DL_File(session, m3u8_url, output_file, input_post_id, output_file_name):
    try:
        # Check if the output file already exists
        if os.path.isfile(output_file):
            # If it exists, rename the file by adding a timestamp to its name
            timestamp = datetime.datetime.now().strftime("%H%M%S")
            base_name, extension = os.path.splitext(output_file)
            new_output_file = f"{base_name}_{timestamp}{extension}"
            os.rename(output_file, new_output_file)
            print(f"Renamed existing file to {new_output_file}")
            print('----------------------------------------------------------------')

        # Use FFmpeg to download and convert the .m3u8 playlist to .mp4
        print("\n")
        process = subprocess.Popen(["ffmpeg", "-i", m3u8_url, "-c:v", "copy", "-c:a", "copy", "-loglevel", "warning", "-stats", output_file])
        
        # Display a loading spinner while the subprocess is running
        spinner = "|/-\\"
        spinner_index = 0
        while process.poll() is None:
            sys.stdout.write("\r" + "Downloading... " + spinner[spinner_index])
            sys.stdout.flush()
            spinner_index = (spinner_index + 1) % len(spinner)
            time.sleep(0.1)
        
        # Clear the loading spinner line
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()
        
        print('----------------------------------------------------------------')
        print(f"Downloaded and converted to {output_file}")
        print('----------------------------------------------------------------')

        # Remove the line with the post ID from the input file
        remove_line_with_id(input_file_path, input_post_id)
        print(f"Removed post ID {input_post_id} from the input file.")

        return True
    except subprocess.CalledProcessError as e:
        print(f"Error while downloading and converting .m3u8 to .mp4: {e}")
        return False
        
# Create a session with custom headers
session = requests.Session()

# Check if the configuration file exists
config_file_path = 'config.ini'

if os.path.isfile(config_file_path):
    # If the config file exists, read the output directory from it
    config = configparser.ConfigParser()
    config.read(config_file_path)
    output_dir = config.get('Settings', 'output_dir')
else:
    # If the config file doesn't exist, prompt the user for the output directory
    output_dir = input("Enter the output directory: ")

    # Create the config file and save the output directory
    config = configparser.ConfigParser()
    config['Settings'] = {'output_dir': output_dir}
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)

# User input to select post IDs from a file or enter a single ID
input_option = input("Choose an option ('file' or 'id'): ").strip().lower()

if input_option == 'file':
    # Read post IDs from a file
    input_file_path = input("Enter the path to the file containing post IDs: ")
    with open(input_file_path, 'r') as id_file:
        post_ids = [line.strip() for line in id_file.readlines()]

    selected_resolution = 'fhd'
    original_resolution = selected_resolution

    # Function to download videos concurrently
    def download_videos_concurrently(session, post_ids, selected_resolution, output_dir):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:  # Adjust max_workers as needed
            futures = []
            for input_post_id in post_ids:
                url = f"https://api.myfans.jp/api/v2/posts/{input_post_id}"
                headers = read_headers_from_file("header.txt")
                response = session.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    main_videos = data['videos']['main']
                    name_creator = data['user']['username']
                    
                    if main_videos:
                        # Check if the selected resolution is available
                        fhd_video = None
                        sd_video = None
                        for video in main_videos:
                            if video["resolution"] == 'fhd':
                                fhd_video = video
                            elif video["resolution"] == 'sd':
                                sd_video = video

                        # Prioritize 'fhd' if available, otherwise use 'sd'
                        if fhd_video:
                            selected_resolution = 'fhd'
                            selected_video = fhd_video
                        elif sd_video:
                            selected_resolution = 'sd'
                            selected_video = sd_video

                        # Continue with the selected resolution
                        video_url = selected_video["url"]

                        # Modify the URL based on the selected resolution
                        video_base_url, video_extension = os.path.splitext(video_url)
                        if selected_resolution == "fhd":
                            target_resolution = "1080p"
                        elif selected_resolution == "sd":
                            target_resolution = "480p"

                        m3u8_url = f"{video_base_url}/{target_resolution}.m3u8"
                        m3u8_response = session.get(m3u8_url, headers=headers)
                        characters = string.ascii_lowercase + string.digits
                        random_string = ''.join(random.choice(characters) for _ in range(6))
                        if video_url and m3u8_response.status_code == 200 and target_resolution == "1080p":
                            m3u8_url = f"{video_base_url}/1080p.m3u8"
                            mp4_output_file = os.path.join(output_dir, f"{name_creator}_video_{random_string}.mp4")
                            # print(f"This video is 1080p")
                            future = executor.submit(DL_File, session, m3u8_url, mp4_output_file, input_post_id, f"{name_creator}_video_{random_string}.mp4")
                            futures.append(future)
                            
                        elif video_url and m3u8_response.status_code == 200 and target_resolution == "480p":
                            m3u8_url = f"{video_base_url}/480p.m3u8"
                            mp4_output_file = os.path.join(output_dir, f"{name_creator}_video_{random_string}.mp4")
                            # print(f"This video is 480p")
                            future = executor.submit(DL_File, session, m3u8_url, mp4_output_file, input_post_id, f"{name_creator}_video_{random_string}.mp4")
                            futures.append(future)
                            
                        else:
                            m3u8_url = f"{video_base_url}/360p.m3u8"
                            mp4_output_file = os.path.join(output_dir, f"{name_creator}_video_{random_string}.mp4")
                            # print(f"This video is 360p")
                            future = executor.submit(DL_File, session, m3u8_url, mp4_output_file, input_post_id, f"{name_creator}_video_{random_string}.mp4")
                            futures.append(future)
                                
                    else:
                        print(f"No videos found or You don't have access to this file for post ID {input_post_id}.")
                else:
                    print(f"Request failed for post ID {input_post_id} with status code:", response.status_code)
            
            # Wait for all download tasks to complete
            concurrent.futures.wait(futures)

    # Call the download_videos_concurrently function to download videos concurrently
    download_videos_concurrently(session, post_ids, selected_resolution, output_dir)

else:
    input_post_id = input("Enter the post ID: ")
    post_ids = [input_post_id]
    selected_resolution = 'fhd'
    original_resolution = selected_resolution

    for input_post_id in post_ids:
        url = f"https://api.myfans.jp/api/v2/posts/{input_post_id}"
        headers = read_headers_from_file("header.txt")
        response = session.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            main_videos = data['videos']['main']
            name_creator = data['user']['username']

            if main_videos:
                # Check if the selected resolution is available
                fhd_video = None
                sd_video = None
                for video in main_videos:
                    if video["resolution"] == 'fhd':
                        fhd_video = video
                    elif video["resolution"] == 'sd':
                        sd_video 
                # Prioritize 'fhd' if available, otherwise use 'sd'
                if fhd_video:
                    selected_resolution = 'fhd'
                    selected_video = fhd_video
                elif sd_video:
                    selected_resolution = 'sd'
                    selected_video = s
                # Continue with the selected resolution
                video_url = selected_video
                # Modify the URL based on the selected resolution
                video_base_url, video_extension = os.path.splitext(video_url)
                if selected_resolution == "fhd":
                    target_resolution = "1080p"
                elif selected_resolution == "sd":
                    target_resolution = "480p"

                # Add /{target_resolution}.m3u8 to the video URL
                m3u8_url = f"{video_base_url}/{target_resolution}.m3u8"
                m3u8_response = session.get(m3u8_url, headers=headers)
                characters = string.ascii_lowercase + string.digits
                random_string = ''.join(random.choice(characters) for _ in range(6))
                if video_url and m3u8_response.status_code == 200 and target_resolution == "1080p":
                    m3u8_url = f"{video_base_url}/1080p.m3u8"
                    mp4_output_file = os.path.join(output_dir, f"{name_creator}_video_{random_string}.mp4")
                    if DL_File(session, m3u8_url, mp4_output_file, input_post_id, f"{name_creator}_video_{random_string}.mp4"):
                        pass
                        
                elif video_url and m3u8_response.status_code == 200 and target_resolution == "480p":
                    m3u8_url = f"{video_base_url}/480p.m3u8"
                    mp4_output_file = os.path.join(output_dir, f"{name_creator}_video_{random_string}.mp4")
                    if DL_File(session, m3u8_url, mp4_output_file, input_post_id, f"{name_creator}_video_{random_string}.mp4"):
                        pass
                        
                else:
                    m3u8_url = f"{video_base_url}/360p.m3u8"
                    mp4_output_file = os.path.join(output_dir, f"{name_creator}_video_{random_string}.mp4")
                    if DL_File(session, m3u8_url, mp4_output_file, input_post_id, f"{name_creator}_video_{random_string}.mp4"):
                        pass

            else:
                print(f"No '{selected_resolution}' videos found in the API response for post ID {input_post_id}.")
        else:
            print(f"Request failed for post ID {input_post_id} with status code:", response.status_code)

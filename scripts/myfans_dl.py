import os
import sys
import time
import requests
import subprocess
import configparser
import concurrent.futures

def read_headers_from_file(filename):
    headers = {}
    with open(filename, 'r') as file:
        for line in file:
            key, value = line.strip().split(': ')
            headers[key.lower()] = value
    return headers

def list_txt_files(directory):
    txt_files = [f for f in os.listdir(directory) if f.endswith('.txt')]
    return txt_files

def choose_file_from_list(files):
    while True:
        for index, file in enumerate(files):
            print(f"{index + 1}. {file}")
        choice = input("Choose a file number (or type '0' to go back): ")
        if choice == '0':
            return None
        if choice.isdigit():
            choice = int(choice) - 1
            if 0 <= choice < len(files):
                return files[choice]
        print("Invalid choice. Please try again.")

def DL_File(session, m3u8_url, output_file, input_post_id, output_folder, output_file_name):
    try:
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        
        if os.path.exists(output_file):
            print(f"File {output_file} already exists. Skipping download.")
            return True

        process = subprocess.Popen(["ffmpeg", "-i", m3u8_url, "-c:v", "copy", "-c:a", "copy", "-loglevel", "error", "-stats", output_file], stderr=subprocess.PIPE, universal_newlines=True)

        while True:
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        process.wait()
        
        print('----------------------------------------------------------------')
        print(f"Downloaded and converted to {output_file}")
        print('----------------------------------------------------------------')

        return True
    except subprocess.CalledProcessError as e:
        print(f"Error while downloading and converting .m3u8 to .mp4: {e}")
        return False

def main():
    session = requests.Session()
    config_file_path = 'config.ini'

    while True:
        if os.path.isfile(config_file_path):
            config = configparser.ConfigParser()
            config.read(config_file_path)
            output_dir = config.get('Settings', 'output_dir')
        else:
            output_dir = input("Enter the output directory: ")
            if output_dir == '0':
                continue
            config = configparser.ConfigParser()
            config['Settings'] = {'output_dir': output_dir}
            with open(config_file_path, 'w') as configfile:
                config.write(configfile)

        while True:
            input_option = input("Choose an option (1 = .txt file, 2 = post id, 0 = go back): ").strip().lower()
            if input_option == '0':
                subprocess.run([sys.executable, "./main.py"])
            elif input_option == '1':
                txt_files = list_txt_files(output_dir)
                if not txt_files:
                    print("No .txt files found in the output directory.")
                    continue
                chosen_file = choose_file_from_list(txt_files)
                if chosen_file is None:
                    continue
                input_file_path = os.path.join(output_dir, chosen_file)
                with open(input_file_path, 'r') as id_file:
                    post_ids = [line.strip() for line in id_file.readlines()]

                selected_resolution = 'fhd'
                original_resolution = selected_resolution

                download_videos_concurrently(session, post_ids, selected_resolution, output_dir)

            elif input_option == '2':
                input_post_id = input("Enter the post ID (or type '0' to go back): ")
                if input_post_id == '0':
                    continue
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
                                
                            video_url = selected_video["url"]
                            video_base_url, video_extension = os.path.splitext(video_url)
                            if selected_resolution == "fhd":
                                target_resolution = "1080p"
                            elif selected_resolution == "sd":
                                target_resolution = "480p"

                            m3u8_url = f"{video_base_url}/{target_resolution}.m3u8"
                            m3u8_response = session.get(m3u8_url, headers=headers)
                            output_folder = os.path.join(output_dir, name_creator)

                            if video_url and m3u8_response.status_code == 200 and target_resolution == "1080p":
                                m3u8_url = f"{video_base_url}/1080p.m3u8"
                                mp4_output_file = os.path.join(output_folder, f"{input_post_id}.mp4")
                                print(f"This video is 1080p")
                                if DL_File(session, m3u8_url, mp4_output_file, input_post_id, output_folder, f"{input_post_id}.mp4"):
                                    pass
                                    
                            elif video_url and m3u8_response.status_code == 200 and target_resolution == "480p":
                                m3u8_url = f"{video_base_url}/480p.m3u8"
                                mp4_output_file = os.path.join(output_folder, f"{input_post_id}.mp4")
                                print(f"This video is 480p")
                                if DL_File(session, m3u8_url, mp4_output_file, input_post_id, output_folder, f"{input_post_id}.mp4"):
                                    pass
                                    
                            else:
                                m3u8_url = f"{video_base_url}/360p.m3u8"
                                mp4_output_file = os.path.join(output_folder, f"{input_post_id}.mp4")
                                print(f"This video is 360p")
                                if DL_File(session, m3u8_url, mp4_output_file, input_post_id, output_folder, f"{input_post_id}.mp4"):
                                    pass

                        else:
                            print(f"No '{selected_resolution}' videos found in the API response for post ID {input_post_id}.")
                    else:
                        print(f"Request failed for post ID {input_post_id} with status code:", response.status_code)
            else:
                print("Invalid option. Please choose 1 or 2.")

def download_videos_concurrently(session, post_ids, selected_resolution, output_dir):
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
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

                    video_url = selected_video["url"]
                    video_base_url, video_extension = os.path.splitext(video_url)
                    if selected_resolution == "fhd":
                        target_resolution = "1080p"
                    elif selected_resolution == "sd":
                        target_resolution = "480p"

                    m3u8_url = f"{video_base_url}/{target_resolution}.m3u8"
                    m3u8_response = session.get(m3u8_url, headers=headers)
                    
                    if video_url and m3u8_response.status_code == 200 and target_resolution == "1080p":
                        m3u8_url = f"{video_base_url}/1080p.m3u8"
                        output_folder = os.path.join(output_dir, name_creator)
                        mp4_output_file = os.path.join(output_folder, f"{input_post_id}.mp4")
                        print(f"This video is 1080p")
                        future = executor.submit(DL_File, session, m3u8_url, mp4_output_file, input_post_id, output_folder, f"{input_post_id}.mp4")
                        futures.append(future)
                        
                    elif video_url and m3u8_response.status_code == 200 and target_resolution == "480p":
                        m3u8_url = f"{video_base_url}/480p.m3u8"
                        output_folder = os.path.join(output_dir, name_creator)
                        mp4_output_file = os.path.join(output_folder, f"{input_post_id}.mp4")
                        print(f"This video is 480p")
                        future = executor.submit(DL_File, session, m3u8_url, mp4_output_file, input_post_id, output_folder, f"{input_post_id}.mp4")
                        futures.append(future)
                        
                    else:
                        m3u8_url = f"{video_base_url}/360p.m3u8"
                        output_folder = os.path.join(output_dir, name_creator)
                        mp4_output_file = os.path.join(output_folder, f"{input_post_id}.mp4")
                        print(f"This video is 360p")
                        future = executor.submit(DL_File, session, m3u8_url, mp4_output_file, input_post_id, output_folder, f"{input_post_id}.mp4")
                        futures.append(future)
                            
                else:
                    print(f"No videos found or You don't have access to this file for post ID {input_post_id}.")
            else:
                print(f"Request failed for post ID {input_post_id} with status code:", response.status_code)
        
        concurrent.futures.wait(futures)

if __name__ == "__main__":
    main()

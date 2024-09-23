import sys

import requests
import json
import os
import configparser
import subprocess

def read_headers_from_file(filename):
    headers = {}
    with open(filename, 'r') as file:
        for line in file:
            key, value = line.strip().split(': ')
            headers[key.lower()] = value
    return headers

def get_posts_for_page(base_url, page, headers):
    url = base_url + str(page)
    response = requests.get(url, headers=headers)
    response.raise_for_status() 
    json_data = response.json()
    return json_data.get("data", [])

def get_output_dir(config_file_path):
    if os.path.isfile(config_file_path):
        config = configparser.ConfigParser()
        config.read(config_file_path)
        return config.get('Settings', 'output_dir')
    else:
        output_dir = input("Enter the output directory: ")
        config = configparser.ConfigParser()
        config['Settings'] = {'output_dir': output_dir}
        with open(config_file_path, 'w') as configfile:
            config.write(configfile)
        return output_dir

def export_ids_to_file(posts, filename, save_free_only):
    if os.path.isfile(filename):
        base, ext = os.path.splitext(filename)
        count = 1
        while os.path.isfile(filename):
            filename = os.path.join(output_dir, f"{base}_{count}{ext}")
            count += 1
    with open(filename, "w") as file:
        for post in posts:
            if save_free_only and not post.get("free"):
                continue
            file.write(f"{post.get('id')}\n")
    print(f"Data exported to {filename}")

config_file_path = 'config.ini'
output_dir = get_output_dir(config_file_path)

while True:
    name_creator = input("Enter a name creator (no require @) or type '0' to go back: ")
    if name_creator.lower() == '0':
        subprocess.run([sys.executable, "./main.py"])
        exit()
    new_base_url = f"https://api.myfans.jp/api/v2/users/show_by_username?username={name_creator}"
    headers = read_headers_from_file("header.txt")
    response = requests.get(new_base_url, headers=headers)
    if response.status_code == 200:
        new_json_data = response.json()
        user_id = new_json_data.get("id")
        if user_id:
            break
        else:
            print("Failed to retrieve user id from the new API endpoint. Please try again.")
    else:
        print("Failed to connect to the API. Please check the username and try again.")

base_url = f"https://api.myfans.jp/api/v2/users/{user_id}/posts?sort_key=publish_start_at&page="

print("Choose the type of posts to display:")
print("1. Video")
print("2. Image")
print("3. Show All")
choice = input("Enter your choice (1/2/3): ")

video_posts = []
image_posts = []

page = 1
while True:
    page_data = get_posts_for_page(base_url, page, headers)
    if not page_data:
        break
    page += 1

    for post in page_data:
        if post.get("kind") == "video":
            video_posts.append(post)
        elif post.get("kind") == "image":
            image_posts.append(post)

    for post in page_data:
        post_id = post.get("id")
        post_kind = post.get("kind")
        humanized_publish_start_at = post.get("humanized_publish_start_at")
        is_free = post.get("free")

        if post_id and post_kind and humanized_publish_start_at:
            if (choice == "1" and post_kind == "video") or \
               (choice == "2" and post_kind == "image") or \
               choice == "3":
                print(f"ID: {post_id}, Type: {post_kind}, Publish Date: {humanized_publish_start_at}, Free: {'yes' if is_free else 'no'}")

video_count = len(video_posts)
image_count = len(image_posts)

if choice == "1":
    print(f"Total Video Count: {video_count}")
elif choice == "2":
    print(f"Total Image Count: {image_count}")
elif choice == "3":
    print(f"Total Video Count: {video_count}")
    print(f"Total Image Count: {image_count}")

export_id_choice = input("Do you want to export 'ID'? (Yes|y/No|n): ").strip().lower()
if export_id_choice in ("yes", "y"):
    save_choice = input("Do you want to save only free posts? (Yes|y/No|n): ").strip().lower()
    save_free_only = save_choice in ("yes", "y")

    if choice in ("1", "3") and video_posts:
        export_ids_to_file(video_posts, os.path.join(output_dir, f"{name_creator}_video_id.txt"), save_free_only)

    if choice in ("2", "3") and image_posts:
        export_ids_to_file(image_posts, os.path.join(output_dir, f"{name_creator}_image_id.txt"), save_free_only)

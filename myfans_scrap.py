import requests
import json
import os
import configparser

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
    json_data = response.json()
    return json_data.get("data", [])

config_file_path = 'config.ini'

if os.path.isfile(config_file_path):
    config = configparser.ConfigParser()
    config.read(config_file_path)
    output_dir = config.get('Settings', 'output_dir')
else:
    output_dir = input("Enter the output directory: ")
    config = configparser.ConfigParser()
    config['Settings'] = {'output_dir': output_dir}
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)

name_creator = input("Enter a name creator (no require @): ")
new_base_url = f"https://api.myfans.jp/api/v2/users/show_by_username?username={name_creator}"
headers = read_headers_from_file("header.txt")
response = requests.get(new_base_url, headers=headers)
new_json_data = response.json()
user_id = new_json_data.get("id")

page = 1
if user_id:
    base_url = f"https://api.myfans.jp/api/v2/users/{user_id}/posts?sort_key=publish_start_at&page="
else:
    print("Failed to retrieve user id from the new API endpoint.")
    exit()

print("Choose the type of posts to display:")
print("1. Video")
print("2. Image")
print("3. Show All")
choice = input("Enter your choice (1/2/3): ")

video_count = 0
image_count = 0
video_posts = []
image_posts = []
all_posts = []

while True:
    page_data = get_posts_for_page(base_url, page, headers)
    
    if not page_data:
        break
    page += 1

    for post in page_data:
        post_kind = post.get("kind")
        if post_kind == "video":
            video_posts.append(post)
        elif post_kind == "image":
            image_posts.append(post)
        all_posts.append(post)

    for post in page_data:
        post_id = post.get("id")
        post_kind = post.get("kind")
        humanized_publish_start_at = post.get("humanized_publish_start_at")
        is_free = post.get("free")

        if post_id and post_kind and humanized_publish_start_at:
            if choice == "1" and post_kind == "video":
                video_count += 1
                print(f"ID: {post_id}, Publish Date: {humanized_publish_start_at}, Free: {'yes' if is_free else 'no'}")
            elif choice == "2" and post_kind == "image":
                image_count += 1
                print(f"ID: {post_id}, Publish Date: {humanized_publish_start_at}, Free: {'yes' if is_free else 'no'}")
            elif choice == "3":
                print(f"ID: {post_id}, Type: {post_kind}, Publish Date: {humanized_publish_start_at}, Free: {'yes' if is_free else 'no'}")
                if post_kind == "video":
                    video_count += 1
                elif post_kind == "image":
                    image_count += 1

if choice == "1":
    print(f"Total Video Count: {video_count}")
if choice == "2":
    print(f"Total Image Count: {image_count}")
if choice == "3":
    print(f"Total Video Count: {video_count}")
    print(f"Total Image Count: {image_count}")

export_id_choice = input("Do you want to export 'ID'? (Yes|y/No|n): ").strip().lower()
if export_id_choice == "yes" or export_id_choice == "y":
    save_choice = input("Do you want to save only free posts? (Yes|y/No|n): ").strip().lower()

    if (choice == "1" or choice == "3") and video_posts:
        filename = os.path.join(output_dir, f"{name_creator}_video_id.txt")
        if os.path.isfile(filename):
            base, ext = os.path.splitext(filename)
            count = 1
            while os.path.isfile(filename):
                filename = os.path.join(output_dir, f"{base}_{count}{ext}")
                count += 1
        with open(filename, "w") as video_posts_id_file:
            for post in video_posts:
                post_id = post.get("id")
                if (save_choice == "yes" or save_choice == "y") and not post.get("free"):
                    continue
                video_posts_id_file.write(f"{post_id}\n")
        print(f"Video data exported to {filename}")

    if (choice == "2" or choice == "3") and image_posts:
        filename = os.path.join(output_dir, f"{name_creator}_image_id.txt")
        if os.path.isfile(filename):
            base, ext = os.path.splitext(filename)
            count = 1
            while os.path.isfile(filename):
                filename = os.path.join(output_dir, f"{base}_{count}{ext}")
                count += 1
        with open(filename, "w") as image_posts_id_file:
            for post in image_posts:
                post_id = post.get("id")
                if (save_choice == "yes" or save_choice == "y") and not post.get("free"):
                    continue
                image_posts_id_file.write(f"{post_id}\n")
        print(f"Image data exported to {filename}")
else:
    exit()

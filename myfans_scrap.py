import requests
import json
import os
import configparser

# Function to read headers from a file and store them in a dictionary
def read_headers_from_file(filename):
    headers = {}
    with open(filename, 'r') as file:
        for line in file:
            key, value = line.strip().split(': ')
            headers[key.lower()] = value
    return headers

# Function to get posts for a specific page
def get_posts_for_page(base_url, page, headers):
    url = base_url + str(page)
    response = requests.get(url, headers=headers)
    json_data = response.json()
    return json_data.get("data", [])

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

# Prompt the user to enter a new username
name_creator = input("Enter a name creator (no require @): ")

# Update the base URL with the new username
new_base_url = f"https://api.myfans.jp/api/v2/users/show_by_username?username={name_creator}"

headers = read_headers_from_file("header.txt")

# Retrieve the "id" from the new API endpoint
response = requests.get(new_base_url, headers=headers)
new_json_data = response.json()
user_id = new_json_data.get("id")

# Define the initial page and base URL
page = 1
if user_id:
    base_url = f"https://api.myfans.jp/api/v2/users/{user_id}/posts?sort_key=publish_start_at&page="
else:
    print("Failed to retrieve user id from the new API endpoint.")
    exit()  # Exit the script if user_id is not available

# Prompt the user to choose what type of posts to display
print("Choose the type of posts to display:")
print("1. Video")
print("2. Image")
print("3. Show All")
choice = input("Enter your choice (1/2/3): ")

# Define dictionaries to store counts for video and image types
video_count = 0
image_count = 0
video_posts = []
image_posts = []
all_posts = []

while True:
    # Retrieve data for the current page
    page_data = get_posts_for_page(base_url, page, headers)
    
    # Check if "pagination" "next" is null
    if not page_data:
        break  # Exit the loop if there's no data on the page
    page += 1

    # Append the posts from the current page to the respective lists
    for post in page_data:
        post_kind = post.get("kind")
        if post_kind == "video":
            video_posts.append(post)
        elif post_kind == "image":
            image_posts.append(post)
        all_posts.append(post)

    # Iterate through the posts in the JSON data for the current page
    for post in page_data:
        post_id = post.get("id")
        post_kind = post.get("kind")
        humanized_publish_start_at = post.get("humanized_publish_start_at")
        is_free = post.get("free")

        if post_id and post_kind and humanized_publish_start_at:
            # Check if the post is a video or an image
            if choice == "1" and post_kind == "video":
                video_count += 1
                print(f"ID: {post_id}, Publish Date: {humanized_publish_start_at}, Free: {'yes' if is_free else 'no'}")
            elif choice == "2" and post_kind == "image":
                image_count += 1
                print(f"ID: {post_id}, Publish Date: {humanized_publish_start_at}, Free: {'yes' if is_free else 'no'}")
            elif choice == "3":
                # Show all posts
                print(f"ID: {post_id}, Type: {post_kind}, Publish Date: {humanized_publish_start_at}, Free: {'yes' if is_free else 'no'}")
                if post_kind == "video":
                    video_count += 1
                elif post_kind == "image":
                    image_count += 1

# Print the total counts for video and image types
if choice == "1":
    print(f"Total Video Count: {video_count}")
if choice == "2":
    print(f"Total Image Count: {image_count}")
if choice == "3":
    print(f"Total Video Count: {video_count}")
    print(f"Total Image Count: {image_count}")

# Export data
export_id_choice = input("Do you want to export 'ID'? (Yes|y/No|n): ").strip().lower()
if export_id_choice == "yes" or export_id_choice == "y":
    save_choice = input("Do you want to save only free posts? (Yes|y/No|n): ").strip().lower()

    if choice == "1" and video_posts:
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
    else:
        exit()

    if choice == "2" and image_posts:
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

    if choice == "3" and all_posts:
        filename = os.path.join(output_dir, f"{name_creator}_all_id.txt")
        if os.path.isfile(filename):
            base, ext = os.path.splitext(filename)
            count = 1
            while os.path.isfile(filename):
                filename = os.path.join(output_dir, f"{base}_{count}{ext}")
                count += 1
        with open(filename, "w") as all_posts_id_file:
            for post in all_posts:
                post_id = post.get("id")
                if (save_choice == "yes" or save_choice == "y") and not post.get("free"):
                    continue
                all_posts_id_file.write(f"{post_id}\n")
        print(f"All data exported to {filename}")
    else:
        exit()
else:
    exit()

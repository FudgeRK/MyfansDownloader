import requests, os, configparser, time
from tqdm import tqdm
from collections import defaultdict
from math import ceil
from io import BytesIO
from PIL import Image

from concurrent.futures import ThreadPoolExecutor

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


save_path = output_dir+"/"+name_creator+"/"
if not os.path.exists(save_path):
    os.makedirs(save_path)

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

# Define dictionaries to store counts for video and image types
image_posts = []

# quick count on number of pages
max_page = 2
min_page = 1
while True:
    if not get_posts_for_page(base_url, max_page, headers):
        #back track min
        while min_page+1 < max_page:
            mid = ceil(0.5*(min_page+max_page))
            if not get_posts_for_page(base_url, mid, headers):
                max_page = mid
            else:
                min_page = mid
        break
    else:
        min_page = max_page
        max_page = max_page*2


for page in tqdm(range(1,min_page+1)):
    # Retrieve data for the current page
    page_data = get_posts_for_page(base_url, page, headers)

    # Append the posts from the current page to the respective lists
    for post in page_data:
        if post.get("kind") == "image":
            image_posts.append(post)

post_count = len(image_posts)


def download_image(url, image_name):
    # if the file already exists, skip
    if os.path.isfile(save_path+image_name):
        return
    try:
        # Send an HTTP request to the URL
        response = requests.get(url)
        
        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Open the image using the PIL library
            img = Image.open(BytesIO(response.content))
            
            # Save the image to the specified path
            img.save(save_path+image_name)
            
            #print(f"Image downloaded : {url}")
        else:
            print(f"Failed to download image. Status code: {response.status_code}")
    except Exception as e:
        print(f"An error occurred: {e}, retry after 5 seconds")
        with ThreadPoolExecutor() as executor:
            executor.submit(download_retry, url, image_name)
            
def download_retry(url, image_name):
    time.sleep(5)
    download_image(url, image_name)

def download_from_post(post, creator):
    try:
        images = post.get("post_images")
        for image in images:
            ext = image['file_url'].split('.')[-1]
            url = image['file_url']
            publish = post['published_at'][:10]
            hash_count[hash(publish)] = hash_count[hash(publish)] + 1
            fname = f"{creator}_{publish}-{hash_count[hash(publish)]}.{ext}"
            download_image(url, fname)
    except Exception as e:
        print(f"An error occurred: {e}")

hash_count = defaultdict(lambda:0)
# Save all images
for post in tqdm(image_posts):
    download_from_post(post, name_creator)
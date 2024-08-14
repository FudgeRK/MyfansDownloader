import os, sys
import subprocess
import zipfile
import requests
from pathlib import Path

def check_ffmpeg_installed():
    try:
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("FFmpeg is already installed.")
            return True
    except FileNotFoundError:
        pass
    return False

def get_latest_ffmpeg_url():
    api_url = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    response = requests.get(api_url)
    response.raise_for_status()
    data = response.json()

    for asset in data['assets']:
        if asset['name'].endswith('full_build.zip'):
            return asset['browser_download_url']
    raise Exception("No FFmpeg zip file found in the latest release.")

def download_ffmpeg_zip(url, download_path):
    response = requests.get(url)
    response.raise_for_status()  
    with open(download_path, 'wb') as file:
        file.write(response.content)
    print(f"Downloaded FFmpeg ZIP to {download_path}")

def unzip_ffmpeg():
    zip_path = "ffmpeg.zip"
    extract_to = "ffmpeg"

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    print(f"Extracted FFmpeg ZIP to {extract_to}")
    
    if os.path.exists(zip_path):
        os.remove(zip_path)
        print(f"Deleted the ZIP file: {zip_path}")
    else:
        print(f"ZIP file not found: {zip_path}")
    return extract_to

def find_bin_folder(extracted_folder):
    for item in os.listdir(extracted_folder):
        item_path = os.path.join(extracted_folder, item)
        if os.path.isdir(item_path):
            bin_folder = os.path.join(item_path, 'bin')
            if os.path.exists(bin_folder):
                return os.path.abspath(bin_folder)
    return None
    
def find_available_powershell():
    powershells = ['pwsh', 'powershell']
    for ps in powershells:
        try:
            result = subprocess.run([ps, '-Command', 'echo test'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                return ps
        except FileNotFoundError:
            continue
    raise Exception("Neither PowerShell nor pwsh is available on this system.")
    
def add_to_path_env(bin_folder):
    powershell = find_available_powershell()
    command = f'{powershell} -Command "[Environment]::SetEnvironmentVariable(\'Path\', [Environment]::GetEnvironmentVariable(\'Path\', \'User\') + \';{bin_folder}\', \'User\')"'
    subprocess.run(command, shell=True, check=True)
    print(f"Updated PATH in user environment variable.")
    print('----------------------------------------------------------------')
    print(f"Please Close the terminal and Re open again :)")
    print('----------------------------------------------------------------')
    sys.exit()

if not check_ffmpeg_installed():
    print("FFmpeg is not installed.")
    ffmpeg_url = get_latest_ffmpeg_url()
    print(f"Latest FFmpeg URL: {ffmpeg_url}")
    download_ffmpeg_zip(ffmpeg_url, "ffmpeg.zip")
    extracted_folder = unzip_ffmpeg()
    bin_folder = find_bin_folder(extracted_folder)
    if bin_folder:
        print(f"Found bin folder at: {bin_folder}")
        add_to_path_env(bin_folder)
    else:
        print("Failed to find the FFmpeg bin directory.")
else:
    pass
    
if __name__ == "__main__":
    main()

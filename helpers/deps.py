import os
import subprocess
import sys
import zipfile

from helpers.prompt import prompt_yes_no


def check_python_version():
    if sys.version_info < (3, 8):
        print("This script requires Python 3.8 or higher!")
        return False
    return True


def check_requirements() -> list:
    """
    Check if the requirements in requirements.txt are installed.
    Returns:
        list: List of missing requirements.
    """
    missing_requirements = []
    try:
        with open('requirements.txt', 'r') as file:
            requirements = file.readlines()
            for requirement in requirements:
                requirement = requirement.strip()
                if requirement:
                    try:
                        subprocess.check_call([sys.executable, '-m', 'pip', 'show', requirement],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except subprocess.CalledProcessError:
                        missing_requirements.append(requirement)
    except FileNotFoundError:
        print("The requirements.txt file was not found.")
    return missing_requirements


def _list_missing_requirements(requirements: list):
    if requirements:
        print("A list of uninstalled packages:")
        for req in requirements:
            print(f"- {req}")


def _prompt_install_missing(requirements: list):
    if requirements:
        _list_missing_requirements(requirements)
        if prompt_yes_no("Do you want to automatically install packages that are not installed?"):
            _install_missing_requirements(requirements)
        else:
            print("There are packages not installed. Please install them manually.")


def _install_missing_requirements(requirements: list):
    for requirement in requirements:
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', requirement])
        except subprocess.CalledProcessError as e:
            print(f"An error occurred during package installation: {e}")


def install_requirements():
    try:
        missing_requirement_lists = check_requirements()
        if missing_requirement_lists:
            _prompt_install_missing(missing_requirement_lists)
    except Exception as e:
        print(f"An error occurred during package installation: {e}")
        return False

    return True


def _is_ffmpeg_installed():
    try:
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("FFmpeg is already installed.")
            return True
    except FileNotFoundError:
        pass
    return False


def _get_latest_ffmpeg_url():
    # Avoid import 'requests' if not needed
    import requests

    api_url = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    response = requests.get(api_url)
    response.raise_for_status()
    data = response.json()

    for asset in data['assets']:
        if asset['name'].endswith('full_build.zip'):
            return asset['browser_download_url']
    raise Exception("No FFmpeg zip file found in the latest release.")


def _download_ffmpeg_zip(url, download_path):
    # Avoid import 'requests' if not needed
    import requests

    response = requests.get(url)
    response.raise_for_status()
    with open(download_path, 'wb') as file:
        file.write(response.content)
    print(f"Downloaded FFmpeg ZIP to {download_path}")


def _unzip_ffmpeg():
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


def _find_bin_folder(extracted_folder):
    for item in os.listdir(extracted_folder):
        item_path = os.path.join(extracted_folder, item)
        if os.path.isdir(item_path):
            bin_folder = os.path.join(item_path, 'bin')
            if os.path.exists(bin_folder):
                return os.path.abspath(bin_folder)
    return None


def _find_available_powershell():
    powershells = ['pwsh', 'powershell']
    for ps in powershells:
        try:
            result = subprocess.run([ps, '-Command', 'echo test'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                return ps
        except FileNotFoundError:
            continue
    raise Exception("Neither PowerShell nor pwsh is available on this system.")


def _add_to_path_env(bin_folder):
    powershell = _find_available_powershell()
    command = f'{powershell} -Command "[Environment]::SetEnvironmentVariable(\'Path\', [Environment]::GetEnvironmentVariable(\'Path\', \'User\') + \';{bin_folder}\', \'User\')"'
    subprocess.run(command, shell=True, check=True)
    print(f"Updated PATH in user environment variable.")
    print('----------------------------------------------------------------')
    print(f"Please Close the terminal and Re open again :)")
    print('----------------------------------------------------------------')
    sys.exit()


def check_ffmpeg_installed():
    if check_requirements():
        # Avoid import 'requests' if not needed
        print("Please install the required packages first.")
        install_requirements()

    if not _is_ffmpeg_installed():
        print("FFmpeg is not installed.")
        ffmpeg_url = _get_latest_ffmpeg_url()

        print(f"Latest FFmpeg URL: {ffmpeg_url}")
        _download_ffmpeg_zip(ffmpeg_url, "ffmpeg.zip")
        extracted_folder = _unzip_ffmpeg()
        bin_folder = _find_bin_folder(extracted_folder)

        if bin_folder:
            print(f"Found bin folder at: {bin_folder}")
            _add_to_path_env(bin_folder)

            return True
        else:
            print("Failed to find the FFmpeg bin directory.")
            return False
    else:
        return True


if __name__ == "__main__":
    install_requirements()
    check_ffmpeg_installed()

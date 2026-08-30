import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from helpers.prompt import prompt_yes_no

ROOT = Path(__file__).resolve().parent.parent

REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
MIN_PYTHON = (3, 9)


def check_python_version():
    if sys.version_info < MIN_PYTHON:
        print("This script requires Python 3.9 or higher!")
        return False
    return True


def parse_requirement_name(requirement: str) -> str:
    line = requirement.strip()
    if not line or line.startswith("#"):
        return ""
    if line.startswith("-"):
        return ""
    match = REQUIREMENT_NAME_RE.match(line)
    return match.group(1) if match else ""


def _requirement_installed(name: str) -> bool:
    try:
        from importlib import metadata
    except ImportError:
        import importlib_metadata as metadata  # type: ignore
    candidates = {name, name.lower(), name.replace("-", "_"), name.replace("_", "-")}
    for candidate in candidates:
        try:
            metadata.version(candidate)
            return True
        except metadata.PackageNotFoundError:
            continue
    try:
        target = name.lower()
        for dist in metadata.distributions():
            dist_name = ""
            try:
                dist_name = dist.metadata["Name"]
            except Exception:
                dist_name = getattr(dist, "name", "") or ""
            if str(dist_name).lower() == target:
                return True
    except Exception:
        return False
    return False


def check_requirements() -> list:
    missing_requirements = []
    try:
        with open(ROOT / "requirements.txt", "r", encoding="utf-8") as file:
            for requirement in file:
                name = parse_requirement_name(requirement)
                if name and not _requirement_installed(name):
                    missing_requirements.append(requirement.strip())
    except FileNotFoundError:
        print("The requirements.txt file was not found.")
    return missing_requirements


def _list_missing_requirements(requirements: list):
    if requirements:
        print("A list of uninstalled packages:")
        for req in requirements:
            print(f"- {req}")


def _prompt_install_missing(requirements: list) -> bool:
    if not requirements:
        return True
    _list_missing_requirements(requirements)
    if prompt_yes_no("Do you want to automatically install packages that are not installed?"):
        return _install_missing_requirements(requirements)
    print("There are packages not installed. Please install them manually.")
    return False


def _install_missing_requirements(requirements: list) -> bool:
    ok = True
    for requirement in requirements:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", requirement])
        except subprocess.CalledProcessError as e:
            print(f"An error occurred during package installation: {e}")
            ok = False
    return ok and not check_requirements()


def install_requirements():
    try:
        missing_requirement_lists = check_requirements()
        if missing_requirement_lists:
            return _prompt_install_missing(missing_requirement_lists)
    except Exception as e:
        print(f"An error occurred during package installation: {e}")
        return False
    return True


def _is_ffmpeg_installed():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
        if result.returncode == 0:
            print("FFmpeg is already installed.")
            return True
    except FileNotFoundError:
        pass
    return False


def _get_latest_ffmpeg_url():
    import requests

    api_url = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    response = requests.get(api_url, timeout=30)
    response.raise_for_status()
    data = response.json()
    for asset in data["assets"]:
        if asset["name"].endswith("full_build.zip"):
            return asset["browser_download_url"]
    raise Exception("No FFmpeg zip file found in the latest release.")


def _download_ffmpeg_zip(url, download_path):
    import requests

    response = requests.get(url, timeout=120)
    response.raise_for_status()
    with open(download_path, "wb") as file:
        file.write(response.content)
    print(f"Downloaded FFmpeg ZIP to {download_path}")


def _unzip_ffmpeg():
    zip_path = "ffmpeg.zip"
    extract_to = "ffmpeg"
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)
    print(f"Extracted FFmpeg ZIP to {extract_to}")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    return extract_to


def _find_bin_folder(extracted_folder):
    for item in os.listdir(extracted_folder):
        item_path = os.path.join(extracted_folder, item)
        if os.path.isdir(item_path):
            bin_folder = os.path.join(item_path, "bin")
            if os.path.exists(bin_folder):
                return os.path.abspath(bin_folder)
    return None


def _find_available_powershell():
    for ps in ("pwsh", "powershell"):
        try:
            result = subprocess.run(
                [ps, "-Command", "echo test"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if result.returncode == 0:
                return ps
        except FileNotFoundError:
            continue
    raise Exception("Neither PowerShell nor pwsh is available on this system.")


def _add_to_path_env(bin_folder):
    powershell = _find_available_powershell()
    script = (
        "[Environment]::SetEnvironmentVariable("
        "'Path', "
        "[Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:MF_FFMPEG_BIN, "
        "'User')"
    )
    env = os.environ.copy()
    env["MF_FFMPEG_BIN"] = str(bin_folder)
    subprocess.run([powershell, "-NoProfile", "-Command", script], check=True, env=env)
    os.environ["PATH"] = str(bin_folder) + os.pathsep + os.environ.get("PATH", "")
    print("Updated PATH in user environment variable.")
    print("----------------------------------------------------------------")
    print("FFmpeg was added to your user PATH. Re-open this terminal if ffmpeg is still not found.")
    print("----------------------------------------------------------------")


def _print_ffmpeg_help():
    print("FFmpeg is required to download videos.")
    print("Install it from one of:")
    print("  Windows: https://www.gyan.dev/ffmpeg/builds/")
    print("  macOS:   brew install ffmpeg")
    print("  Debian:  sudo apt install ffmpeg")


def check_ffmpeg_installed():
    if _is_ffmpeg_installed():
        return True

    print("FFmpeg is not installed.")
    if os.name != "nt":
        _print_ffmpeg_help()
        return False

    if not prompt_yes_no("Download and install a Windows FFmpeg build now?"):
        _print_ffmpeg_help()
        return False

    try:
        ffmpeg_url = _get_latest_ffmpeg_url()
        print(f"Latest FFmpeg URL: {ffmpeg_url}")
        _download_ffmpeg_zip(ffmpeg_url, "ffmpeg.zip")
        extracted_folder = _unzip_ffmpeg()
        bin_folder = _find_bin_folder(extracted_folder)
        if not bin_folder:
            print("Failed to find the FFmpeg bin directory.")
            return False
        print(f"Found bin folder at: {bin_folder}")
        _add_to_path_env(bin_folder)
        return _is_ffmpeg_installed()
    except Exception as exc:
        print(f"Automatic FFmpeg install failed: {exc}")
        _print_ffmpeg_help()
        return False


if __name__ == "__main__":
    install_requirements()
    check_ffmpeg_installed()

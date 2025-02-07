import sys
import subprocess
from helpers.deps import install_requirements, check_python_version, check_ffmpeg_installed

def option1():
    subprocess.run([sys.executable, "scripts/myfans_dl.py"])

def option2():
    subprocess.run([sys.executable, "scripts/myfans_image_dl.py"]) 

def main():
    # Check if the required packages are installed and if ffmpeg is installed.
    if not install_requirements() or not check_ffmpeg_installed():
        sys.exit(1)

    options = {
        "1": option1,
        "2": option2
    }

    print("Choose an option:")
    print("1. Download videos")
    print("2. Download images")

    choice = input("Enter your choice (1 or 2): ")
    action = options.get(choice)

    if action:
        action()
    else:
        print("Invalid choice. Please enter 1 or 2")

if __name__ == "__main__":
    if check_python_version():
        main()

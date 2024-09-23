import sys
import subprocess
from scripts.check_ffmpeg import *


def option1():
    subprocess.run([sys.executable, "scripts/myfans_scrap.py"])


def option2():
    subprocess.run([sys.executable, "scripts/myfans_dl.py"])


def option3():
    subprocess.run([sys.executable, "scripts/myfans_image_dl.py"])


def main():
    options = {
        "1": option1,
        "2": option2,
        "3": option3
    }

    print("Choose an option:")
    print("1. Scrap post id")
    print("2. Download videos")
    print("3. Download images")

    choice = input("Enter your choice (1, 2 or 3): ")
    action = options.get(choice)

    if action:
        action()
    else:
        print("Invalid choice. Please enter 1, 2 or 3")


if __name__ == "__main__":
    main()

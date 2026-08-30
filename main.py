import sys

from helpers.deps import check_ffmpeg_installed, check_python_version, install_requirements


def option1():
    from scripts.myfans_dl import main as video_main

    video_main()


def option2():
    from scripts.myfans_image_dl import main as image_main

    image_main()


def option3():
    from app import app

    print("Starting web server on http://127.0.0.1:5000")
    print("Press Ctrl+C to stop the server")
    app.run(host="127.0.0.1", port=5000, debug=False)


def main():
    if not install_requirements() or not check_ffmpeg_installed():
        sys.exit(1)

    options = {
        "1": option1,
        "2": option2,
        "3": option3,
    }

    print("Choose an option:")
    print("1. Download videos")
    print("2. Download images")
    print("3. Web interface")

    choice = input("Enter your choice (1, 2, or 3): ").strip()
    action = options.get(choice)
    if action:
        action()
    else:
        print("Invalid choice. Please enter 1, 2, or 3")


if __name__ == "__main__":
    if check_python_version():
        try:
            main()
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)

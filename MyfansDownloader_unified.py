#!/usr/bin/env python3
"""
Unified MyfansDownloader - Single Program
Combines CLI and Web Interface
"""
import sys
import webbrowser
import time
from pathlib import Path

# Add current directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent))

from helpers.deps import install_requirements, check_python_version, check_ffmpeg_installed

def run_cli_mode():
    """Run the CLI downloader"""
    try:
        print("\n" + "="*50)
        print("MyfansDownloader - CLI Mode")
        print("="*50 + "\n")
        
        print("Choose an option:")
        print("1. Download videos")
        print("2. Download images")
        
        choice = input("\nEnter your choice (1 or 2): ").strip()
        
        if choice == "1":
            from scripts.myfans_dl import main as video_main
            print("\nRunning Download videos...\n")
            video_main()
        elif choice == "2":
            from scripts.myfans_image_dl import main as image_main
            print("\nRunning Download images...\n")
            image_main()
        else:
            print("Invalid choice. Please enter 1 or 2")
    except Exception as e:
        print(f"Error in CLI mode: {e}")

def run_web_mode():
    """Run the Flask web server"""
    try:
        print("\n" + "="*50)
        print("MyfansDownloader - Web Mode")
        print("="*50 + "\n")
        
        from app import app
        
        port = 5000
        url = f"http://localhost:{port}"
        
        print(f"Starting web server on {url}")
        print("Opening browser in 2 seconds...")
        
        # Open browser after a short delay
        time.sleep(2)
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Could not open browser automatically: {e}")
            print(f"Please visit {url} manually")
        
        print("\nPress Ctrl+C to stop the server\n")
        app.run(host='localhost', port=port, debug=False)
        
    except Exception as e:
        print(f"Error in web mode: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main entry point"""
    # Check Python version
    if not check_python_version():
        print("Python version check failed")
        sys.exit(1)
    
    # Install requirements
    if not install_requirements():
        print("Failed to install requirements")
        sys.exit(1)
    
    # Check FFmpeg
    if not check_ffmpeg_installed():
        print("FFmpeg is not installed. Please install FFmpeg to continue.")
        sys.exit(1)
    
    # Main menu
    while True:
        print("\n" + "="*50)
        print("MyfansDownloader - Main Menu")
        print("="*50)
        print("\nSelect mode:")
        print("1. CLI Mode (Download videos/images)")
        print("2. Web Mode (Web interface)")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1, 2, or 3): ").strip()
        
        if choice == "1":
            run_cli_mode()
        elif choice == "2":
            run_web_mode()
        elif choice == "3":
            print("\nExiting MyfansDownloader. Goodbye!")
            sys.exit(0)
        else:
            print("Invalid choice. Please enter 1, 2, or 3")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram interrupted. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

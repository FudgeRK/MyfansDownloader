import subprocess
import sys


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
        choice = input("Do you want to automatically install packages that are not installed? (Yes|y/No|n): ").strip().lower()
        if choice in ('yes', 'y'):
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


if __name__ == "__main__":
    missing = check_requirements()
    _prompt_install_missing(missing)

import subprocess

def option1():
    subprocess.run(["python", "scripts/myfans_scrap.py"])

def option2():
    subprocess.run(["python", "scripts/myfans_dl.py"])
    
def option3():
    subprocess.run(["python", "scripts/myfans_image_dl.py"])

def main():
    print("Choose an option:")
    print("1. Scrap post id")
    print("2. Download videos")
    print("3. Download images")
    
    choice = input("Enter your choice (1, 2 or 3): ")
    
    if choice == "1":
        option1()
    elif choice == "2":
        option2()
    elif choice == "3":
        option2()    
    else:
        print("Invalid choice. Please enter 1, 2 or 3")

if __name__ == "__main__":
    main()

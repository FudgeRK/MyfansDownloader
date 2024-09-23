# input("Do you want to export 'ID'? (Yes|y/No|n): ").strip().lower()

def prompt_yes_no(prompt: str) -> bool:
    while True:
        choice = input(f"{prompt} ( Yes|y / No|n ): ").strip().lower()

        if choice in ('yes', 'y'):
            return True
        elif choice in ('no', 'n'):
            return False

        print("\nInvalid choice. Please enter 'Yes(y)' or 'No(n)'.\n")

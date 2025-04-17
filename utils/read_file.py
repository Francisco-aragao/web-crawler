
def read_seeds_file(seeds_file: str):
    try:
        with open(seeds_file, 'r') as f:
            seeds = [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        print(f"Error: The file {seeds_file} was not found.")
        return
    except Exception as e:
        print(f"Error: {e}")
        return
    
    if not seeds:
        print("Error: The seeds file is empty.")
        return
    
    return seeds
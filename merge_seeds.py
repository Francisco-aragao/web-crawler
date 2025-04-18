import os

def load_all_files_from_folder(folder_path: str) -> list[str]:
    contents = []

    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)

        if os.path.isfile(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                contents.append(f.read())

    return contents

merged = load_all_files_from_folder("seeds")

with open("seeds/merged.txt", "w", encoding="utf-8") as f:
    for content in merged:
        f.write(content)
import os

def extract_urls_from_warc_files(folder_path: str, output_file: str):
    urls = []

    for idx in range(1, 88):  # From 1 to 75 inclusive
        filename = os.path.join(folder_path, f"corpus_{idx}.warc")
        
        if not os.path.exists(filename):
            print(f"Warning: File {filename} does not exist, skipping.")
            continue

        with open(filename, 'r', encoding='utf-8', errors='ignore') as warc_file:
            for line in warc_file:
                if line.startswith("WARC-Target-URI:"):
                    url = line[len("WARC-Target-URI:"):].strip()
                    if url:  # Avoid empty lines
                        urls.append(url)

    # Save all URLs to a .txt file
    with open(output_file, 'w', encoding='utf-8') as out_file:
        for url in urls:
            out_file.write(url + '\n')

    print(f"Extracted {len(urls)} URLs and saved to {output_file}.")

if __name__ == "__main__":
    # Folder where your corpus_*.warc files are located
    folder_path = "./corpus/"  # <-- adjust if needed
    output_file = "extracted_urls.txt"
    
    extract_urls_from_warc_files(folder_path, output_file)

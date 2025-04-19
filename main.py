import argparse
from utils.read_file import read_seeds_file
from crawler import Crawler
import json

MAX_WORKERS = 15

def get_initial_arguments():
    parser = argparse.ArgumentParser(description="""
                                     Web Crawler for Project Assignment 1 in Information Retrieval.
                                     
                                     To run, just type:

                                     python3 main.py -s <SEEDS> -n <LIMIT> [-d]
                                     """)
    
    parser.add_argument('-s', '--seeds', type=str, required=True, help='Path to the seeds file')
    parser.add_argument('-n', '--limit', type=int, required=True, help='Number of pages to crawl')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('-c', '--debug_code', action='store_true', help='Enable debug mode from code')
    parser.add_argument('-sr', '--store_results', action='store_true', help='Store final results')

    args = parser.parse_args()

    return args

def main():
    args = get_initial_arguments()

    seeds_file = read_seeds_file(args.seeds)

    if seeds_file is None:
        print(f"Error: Unable to read seeds file {args.seeds}.")
        return

    crawler = Crawler(seeds_file, args.limit, args.debug, args.debug_code)

    crawler.init(MAX_WORKERS)

    if args.store_results:
        with open('visited_urls.json', 'w') as f:
            json.dump(list(crawler.visited_urls), f, indent=4)
        
        with open('domain_count.json', 'w') as f:
            json.dump(crawler.domain_count, f, indent=4)
        
        with open('tokens_by_page.json', 'w') as f:
            json.dump(crawler.number_tokens_per_page, f, indent=4)

        with open(f'time_per_block_THREADS:{MAX_WORKERS}.json', 'w') as f:
            json.dump(list(crawler.time_per_block), f, indent=4)

        print("Length of visited URLs:", len(crawler.visited_urls))
    

if __name__ == "__main__":
    main()
    
import argparse
from utils.read_file import read_seeds_file
from crawler import Crawler

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

    args = parser.parse_args()

    return args

def main():
    args = get_initial_arguments()

    seeds_file = read_seeds_file(args.seeds)

    crawler = Crawler(seeds_file, args.limit, args.debug, args.debug_code)

    crawler.init()
    

if __name__ == "__main__":
    main()
    
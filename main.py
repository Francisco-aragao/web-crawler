import argparse

def get_initial_arguments():
    parser = argparse.ArgumentParser(description="""
                                     Web Crawler for Project Assignment 1 in Information Retrieval.
                                     
                                     To run, just type:

                                     python3 main.py -s <SEEDS> -n <LIMIT> [-d]
                                     """)
    
    parser.add_argument('-s', '--seeds', type=str, required=True, help='Path to the seeds file')
    parser.add_argument('-n', '--limit', type=int, required=True, help='Number of pages to crawl')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    if args.debug:
        print("Debug mode is enabled.")

    return args

def main():
    args = get_initial_arguments()

    if args.debug:
        print("oi)")

if __name__ == "__main__":
    main()
    
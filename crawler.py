from collections import deque
from bs4 import BeautifulSoup
import requests
from datetime import datetime
from utils.debug_output import DebugOutput
from protego import Protego
import time
from url_normalize import url_normalize
from urllib.parse import urljoin, urlparse
import gzip
from io import BytesIO
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import json

DATE_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
TIMEOUT_LIMIT = 7 # timeout for requests
CORPUS_OUTPUT_FOLDER = "corpus"
NUMBER_OF_ENTRIES_IN_WARC_FILE = 1000
MIN_DELAY = 0.1 # seconds between requests
PERCENTAGE_BR_LINKS = 0.6 # percentage of BR links to crawl
PERCENTAGE_EXTERNAL_LINKS = 0.2 

lock = Lock()

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session_with_retries(max_retries=2, status_forcelist=(500, 502, 504)):
    """
        This function creates a request session with just 2 retries for the `status_forcelist` return codes.

        This will avoid creating a new session for each request and too much retries.
    """

    session = requests.Session()
    retries = Retry(
        total=max_retries,
        status_forcelist=status_forcelist,
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

session = create_session_with_retries()


class Crawler:

    """
        Class to handle all crawling operations.
    """

    def __init__(self, seeds: list, limit: int, debug: bool, debug_code: bool):
        self.seeds = seeds # initial URLs to crawl
        self.limit = limit # maximum number of pages to crawl
        self.len_crawled_data = 0 # number of pages crawled
        self.visited_urls_per_domain = {} # dictionary to store visited URLs per domain
        self.crawled_data = [] # list to store crawled data
        self.frontier_external = deque() # external URLs to crawl
        self.frontier_internal = deque() # internal URLs to crawl
        self.br_urls = deque() # BR URLs to crawl
        self.debug = debug # flag to enable debug mode
        self.debug_code = debug_code # flag to enable debug code
        self.domain_count = {} # dictionary to store the number of subpages per domain
        self.robots_txt_per_domain = {} # dictionary to store robots.txt files per domain
        self.number_tokens_per_page = {} # dictionary to store the number of tokens per page
        self.time_per_block = [] # storing time spent for block
        self.next_allowed_access = {} # dictionary to store the next allowed access time for each domain (delay from robots txt)

        for seed in seeds: # add initial seeds to the frontier
            self.frontier_external.append(seed)

    def crawl_one_url(self, url: str) -> dict | None:

        """
            Crawl a single URL and return the crawled data.

            This function will check if the URL is already visited, fetch the page, parse it and extract links.
        """

        if self.debug_code:
            print(f"\nVisiting {url}...")

        if url.startswith(("mailto:", "tel:", "javascript:")): # skip not valid links
            if self.debug_code:
                print(f"Skipping {url} due to unsupported scheme.")
            return None
        
        url = url.split('?')[0]  # remove query parameters
        url = url.split('#')[0]  # remove HTML ids

        url_normalized = self.normalize_url(url) # normalize the URL to check if it is already visited
        if url_normalized is None:
            return None

        parsed = urlparse(url_normalized)
        domain = parsed.hostname

        with lock: # verifies if the URL is already visited # REVISITATION POLICY
            if domain in self.visited_urls_per_domain:
                if url_normalized in self.visited_urls_per_domain[domain]: # if the domain and URL are already visited -> skip
                    return None
                self.visited_urls_per_domain[domain].add(url_normalized)
            else:
                self.visited_urls_per_domain[domain] = {url_normalized}

        domain_url = f"{parsed.scheme}://{domain}" if domain else url_normalized

        # get the robots.txt file for the domain and stores it
        now = time.time()
        robots_txt = self.robots_txt_per_domain.get(domain)
        if not robots_txt:
            robots_txt = self.get_robots_txt(domain_url)
            
            with lock:
                if robots_txt:
                    self.robots_txt_per_domain[domain] = robots_txt
        else: 
            # robots txt exists, so i will check if the delay is ok
            if domain in self.next_allowed_access and now < self.next_allowed_access[domain]: # POLITENESS POLICY
                self.frontier_internal.append(url)  # Requeue the URL for later
                return None
        
        # skip if the URL is not crawlable
        if not self.is_crawlable(url_normalized, robots_txt):
            return None

        # get web content
        fetch = self.fetch_url(url_normalized)
        if fetch is None:
            return None
        
        delay = robots_txt.crawl_delay('*') if robots_txt else None
        delay = delay if delay else MIN_DELAY # set a default delay if not specified
        self.next_allowed_access[domain] = now + delay # store the delay from robots txt

        text, headers = fetch
        page = self.parser_content_to_html(url_normalized, text, headers)
        if page is None:
            return None

        # get text content to perform the token count
        text_content_page = page.get_text(separator=' ', strip=True)
        token_count = len(text_content_page)

        # extracting links from the page
        links = self.extract_links(url_normalized, page)

        # returning the crawled data
        return {
            "url": url_normalized,
            "page": page,
            "headers": headers,
            "tokens": token_count,
            "domain": domain,
            "links": links,
        }
    
    def get_urls_to_crawl(self, MAX_WORKERS) -> list:

        """
            This function will only return the URLs to crawl based on the priorities:
            1. BR URLs
            2. External URLs
            3. Internal URLs
        """

        urls = []

        len_br = int(PERCENTAGE_BR_LINKS * (MAX_WORKERS))
        len_external = int(PERCENTAGE_EXTERNAL_LINKS * (MAX_WORKERS - len_br))
        len_internal = MAX_WORKERS - len_external - len_br

        for _ in range(len_br):
            if self.br_urls:
                urls.append(self.br_urls.pop())

        for _ in range(len_external):
            if self.frontier_external:
                urls.append(self.frontier_external.pop())

        for _ in range(len_internal):
            if self.frontier_internal:
                urls.append(self.frontier_internal.pop())

        remaining_urls = MAX_WORKERS - len(urls)

        # fill the remaining URLs with any frontier, prioritizing br -> external -> internal
        for _ in range(remaining_urls):
            if self.br_urls:
                urls.append(self.br_urls.pop())
            elif self.frontier_external:
                urls.append(self.frontier_external.pop())
            elif self.frontier_internal:
                urls.append(self.frontier_internal.pop())

        return urls
    
    def init(self, MAX_WORKERS):
        """
            Initial function to start the crawl.
            This function will manage the URLs for each thread, merge the results and store the data in WARC format.
        """

        index_files = 1 # index of the WARC file 
        block = 0
        start_time = time.time()

        if self.debug_code:
            print(f"Starting crawl with {MAX_WORKERS} threads...")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor: # PARALLELIZATION POLICY
            while self.len_crawled_data <= self.limit and index_files <= (self.limit/NUMBER_OF_ENTRIES_IN_WARC_FILE): # finishing the crawl
                
                if self.debug_code:
                    print(f"Current number of crawled pages: {self.len_crawled_data}")
                
                if (not self.frontier_external and not self.frontier_internal and not self.br_urls): # no more URLs to crawl
                    if self.debug_code:
                        print("No more URLs to crawl, exiting.")
                    return 
                
                # get the URLs to crawl
                urls = self.get_urls_to_crawl(MAX_WORKERS)              

                # crawl the URLs in parallel
                futures = [executor.submit(self.crawl_one_url, url) for url in urls]

                # merge results
                for future in as_completed(futures):
                    result = future.result()
                    if result is None:
                        continue
                    
                    with lock:
                        if self.len_crawled_data >= self.limit: # stoping threads
                            if self.debug_code:
                                print("Crawling limit reached, stopping.")
                            break

                    url = result["url"]
                    page = result["page"]
                    headers = result["headers"]
                    tokens = result["tokens"]
                    domain = result["domain"]
                    links = result["links"]

                    # storing the crawled data
                    with lock:
                        self.crawled_data.append((url, page, headers))
                        self.len_crawled_data += 1
                        self.number_tokens_per_page[url] = tokens
                        self.domain_count[domain] = self.domain_count.get(domain, 0) + 1

                    # collecting the links on the page
                    # there is no need to lock it because it is not important to the algorith verification
                    if links:
                        for link in links:
                            normalized = self.normalize_url(link)
                            if not normalized:
                                continue
                            link_domain = urlparse(normalized).hostname
                            if not link_domain:
                                continue
                            
                            # filtering the collected links
                            if '.br' in link_domain:
                                self.add_to_frontier_if_possible(normalized, "br")
                            else:
                            
                                link_type = (
                                    "internal"
                                    if domain and (link_domain == domain or link_domain.endswith(f".{domain}") or link_domain.startswith(f"www.{domain}"))
                                    else "external"
                                )
                                self.add_to_frontier_if_possible(normalized, link_type)

                    # storing the crawled data in the WARC file
                    block += 1 
                    block, index_files = self.store_results(block, index_files, start_time, MAX_WORKERS) # STORAGE POLICY
                    current_time = time.time()
                    start_time = current_time
    
    def store_results(self, block, index_files, start_time, MAX_WORKERS):
        """
            Store the results in WARC format and compress it to .gz.

            Return the block number (0 if reached the limit) and the index of the WARC file (will not change if the block limit was not reached).
        """
        
        if block >= NUMBER_OF_ENTRIES_IN_WARC_FILE:
            self.write_warc_and_gz(index_files)
            index_files += 1
            block = 0
            current_time = time.time()
            self.time_per_block.append(current_time - start_time)
            
            self.crawled_data = []  # cleans crawled data -> free memory

            if self.debug_code:
                with open('visited_urls.json', 'w') as f:
                    json.dump(list(self.visited_urls_per_domain), f, indent=4)
                
                with open('domain_count.json', 'w') as f:
                    json.dump(self.domain_count, f, indent=4)
                
                with open('tokens_by_page.json', 'w') as f:
                    json.dump(self.number_tokens_per_page, f, indent=4)

                with open(f'time_per_block_THREADS:{MAX_WORKERS}.json', 'w') as f:
                    json.dump(list(self.time_per_block), f, indent=4)
        
        return block, index_files


    def sanitize_header(self, header_value: str) -> str:
        """
            Sanitize the header value to ensure it is ASCII encoded.
        """

        try:
            return header_value.encode('ascii', 'replace').decode('ascii')
        except UnicodeEncodeError:
            return ''.join([ch if ord(ch) < 128 else '?' for ch in header_value])
    
    def write_warc_and_gz(self, index: int) -> None:

        """
            Write the WARC file and compress it to .gz format.
        """

        warc_filename = f"{CORPUS_OUTPUT_FOLDER}/corpus_{index}.warc"
        gz_filename = f"{warc_filename}.gz"

        # Write uncompressed WARC
        with open(warc_filename, "wb") as warc_file:
            writer = WARCWriter(warc_file, gzip=False)

            for url, html, headers in self.crawled_data: # iterate over all crawled data and store the content

                try:
                    header_fixed = []
                    for key, value in headers.items():
                        # not all headers have the same format, so this code will fix it
                        header_fixed.append((self.sanitize_header(key), self.sanitize_header(value))) 

                    http_headers = StatusAndHeaders("200 OK", header_fixed, protocol="HTTP/1.0")
                except Exception as e:
                    http_headers = StatusAndHeaders("200 OK", [], protocol="HTTP/1.0")

                try:
                    record = writer.create_warc_record(
                        url,
                        "response",
                        payload=BytesIO(html.encode("utf-8")),
                        http_headers=http_headers
                    )

                    writer.write_record(record)
                except Exception as e:
                    continue

        # Compress the WARC to .gz
        with open(warc_filename, "rb") as f_in, gzip.open(gz_filename, "wb") as f_out:
            f_out.writelines(f_in)
        

    def normalize_url(self, url: str) -> str | None:

        """
            Normalize the URL removing bad characters.
        """ 

        try:
            normalized_url = url_normalize(url)
        
        except Exception as e:
            normalized_url = None

        if not normalized_url:
            if self.debug_code:
                print(f"Failed to normalize URL {url}, skipping.")
            return

        return normalized_url
    
    def add_to_frontier_if_possible(self, url: str, type: str) -> None:

        """
            Add the URL to the frontier if it is not already present.

            The type can be "internal", "external" or "br".

            Internal = same domain
            External = different domain
            BR = .br domain

            This division is useful to balance the crawl performance x novelty
        """

        if type == "br":
            if url not in self.br_urls:
                self.br_urls.append(url)    

            if self.debug_code:
                print(f"Added {url} to br_urls.")
        elif type == "internal":
            if url not in self.frontier_internal:
                self.frontier_internal.append(url)    

            if self.debug_code:
                print(f"Added {url} to frontier.")
        else:
            if url not in self.frontier_external:
                self.frontier_external.append(url)    

            if self.debug_code:
                print(f"Added {url} to frontier_external.")

        return 
    
    def is_crawlable(self, url: str, robots_txt: Protego | None) -> bool:
        
        """
            Check if the URL is crawlable according to the robots.txt file.

            If no robots.txt file is found, it will return True.
        """

        if robots_txt is None:
            if self.debug_code:
                print(f"Robots.txt not found for {url}.")
            return True
        
        if not robots_txt.can_fetch('*', url):
            if self.debug_code:
                print(f"Robots.txt disallows crawling {url}, skipping.")
            return False

        return True

    
    def get_robots_txt(self, url: str) -> Protego | None:

        """
            Fetch the robots.txt file for the URL.

            The URL used is <base URL>/robots.txt.
        """

        robots_txt_url = urljoin(url, '/robots.txt')
        try:
            response = session.get(robots_txt_url, timeout=TIMEOUT_LIMIT)
            if not response or not response.status_code == 200:
                if self.debug_code:
                    print(f"Failed to fetch robots.txt from {robots_txt_url}, skipping.")
                return None
            
            parser: Protego = Protego.parse(response.text)

            return parser
        
        except Exception as e:
            return None

    def fetch_url(self, url: str) -> tuple | None:

        """
            Fetch the URL and return the content and headers.

            This will be useful to check if the page is HTML or not and to store the content in WARC format.
        """

        try:
            response = session.get(url, timeout=TIMEOUT_LIMIT)

            if not response: 
                if self.debug_code:
                    print(f"Failed to fetch {url}, skipping.")
                return None

            content_type = response.headers.get('Content-Type', '')

            if not content_type or 'text/html' not in content_type or response.status_code != 200:
                if self.debug_code:
                    print(f"Content type {content_type} not supported for {url}, or error in request. Skipping.")
                return None            
            
            return response.text, response.headers
        
        except Exception as e:
            if self.debug_code:
                print(f"Request failed: {e}")
            return None

    def parser_content_to_html(self, url, text, headers) -> BeautifulSoup | None:

        """
            Parser the page content to HTML. Skips if the page is not HTML.
        """

        page : BeautifulSoup = BeautifulSoup(text, 'html.parser')

        if not page: # SELECTION POLICY
            if self.debug_code:
                print(f"Failed to parse HTML for {url}, skipping.")
            return None
        
        if self.debug:
            try:
                title = page.title.string if page.title else "No title"
                text = page.get_text()
                text = ' '.join(text.split()[:20])
                timestamp = headers.get('Date', 'No date')
                timestamp_unix = int(datetime.strptime(timestamp, DATE_FORMAT).timestamp())
            except Exception as e:
                return None

            print(DebugOutput(url, title, text, timestamp_unix))
        
        return page

    def extract_links(self, base_url: str, page: BeautifulSoup) -> list[str] | None:

        """
            Extract all links from the page.
        """

        links = set(page.find_all('a', href=True))

        if not links:
            if self.debug_code:
                print(f"No links found in {base_url}, skipping.")
            return None

        filtered_links = []

        for tag in links:
            href = tag['href']

            if not href or href.startswith(('mailto:', 'tel:', 'javascript:')): # skip not valid links
                continue

            if not href.startswith(('http://', 'https://')): # handles prefixes
                full_link = urljoin(base_url, href)
            else:
                full_link = href

            filtered_links.append(full_link)

        if self.debug_code:
            print(f"Filtered links: {filtered_links}")

        return filtered_links
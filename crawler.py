from collections import deque
from bs4 import BeautifulSoup
import requests
from datetime import datetime
from debug_output import DebugOutput
from protego import Protego
import time
from url_normalize import url_normalize
from urllib.parse import urljoin, urlparse
import json
import gzip
from io import BytesIO
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

DATE_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
MAX_SAME_DOMAIN_VISITS = 30 # max number of visits to the same domain
TIMEOUT_LIMIT = 7
CORPUS_OUTPUT_FOLDER = "corpus"
NUMBER_OF_ENTRIES_IN_WARC_FILE = 1000
MIN_DELAY = 0.1 # seconds between requests

lock = Lock()

class Crawler:
    def __init__(self, seeds: list, limit: int, debug: bool, debug_code: bool):
        self.seeds = seeds
        self.limit = limit
        self.len_crawled_data = 0
        self.visited_urls = set()
        self.crawled_data = []
        self.frontier = deque()
        self.debug = debug
        self.debug_code = debug_code
        self.domain_count = {}
        self.robots_txt_per_domain = {}
        self.number_tokens_per_page = {}
        self.time_per_block = []

        for seed in seeds:
            self.frontier.append(seed)


    def crawl_one_url(self, url: str) -> bool:
        if self.debug_code:
            print(f"\nVisiting {url}...")

        if self.is_visited(url):
            return False

        url_normalized = self.normalize_url(url)
        
        if url_normalized is None:
            return False

        domain = urlparse(url_normalized).hostname
        
        if domain and domain in self.robots_txt_per_domain:
            robots_txt = self.robots_txt_per_domain[domain]
        else:
            robots_txt = self.get_robots_txt(domain if domain else url_normalized)
            if robots_txt:
                lock.acquire()
                self.robots_txt_per_domain[domain] = robots_txt
                lock.release()

            lock.acquire()
            
            if domain not in self.domain_count:
                self.domain_count[domain] = 1
                lock.release()
            else:
                self.domain_count[domain] += 1
                lock.release()
                
                if self.domain_count[domain] > MAX_SAME_DOMAIN_VISITS:
                    if self.debug_code:
                        print(f"Domain {domain} has exceeded the limit, skipping.")
                    
                    return False
        
                delay = robots_txt.crawl_delay('*')  if robots_txt else None

                if delay:
                    print(delay)
                    print(robots_txt)
                    raise

                if self.debug_code:
                    print(f"Delaying.")

                time.sleep(float(delay) if delay else MIN_DELAY) # espero delay especificado no robots.txt ou então delay minimo 


        if not self.is_crawlable(url, robots_txt):
            return False

        fetch = self.fetch_url(url)
        if fetch is None:
            return False

        text, headers = fetch
        page = self.parser_content_to_html(url, text, headers)
        if page is None:
            return False

        lock.acquire()
        self.crawled_data.append((url, page, headers))
        self.visited_urls.add(url_normalized)
        self.len_crawled_data += 1
        self.number_tokens_per_page[url] = len(page.get_text().split())    # PRECISO CONFERIR ISSO AQUI
        lock.release()

        if self.debug_code:
            print(f"Total visited: {len(self.visited_urls)}")

        links = self.extract_links(url_normalized, page)
        if links:
            for link in links:
                link_normalized = self.normalize_url(link)
                if link_normalized and not self.is_visited(link_normalized):
                    lock.acquire()
                    self.add_to_frontier_if_possible(link_normalized)
                    lock.release()

        return True
    
    def init(self, MAX_WORKERS):
        index_files = 1
        block = 0

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while self.len_crawled_data <= self.limit and self.frontier:
                urls = []
                while self.frontier and len(urls) < MAX_WORKERS:
                    urls.append(self.frontier.pop())

                threads = [executor.submit(self.crawl_one_url, url) for url in urls]

                for th in as_completed(threads):
                    if th.result():
                        block += 1

                if block >= NUMBER_OF_ENTRIES_IN_WARC_FILE:
                    self.write_warc_and_gz(index_files)
                    index_files += 1
                    block = 0  
                    self.time_per_block.append(time.time() - start_time)
                    start_time = time.time()
                

    """ def init(self):

        block = 0
        index_files = 1
        while self.len_crawled_data <= self.limit:

            if len(self.frontier) == 0:
                if self.debug_code: 
                    print("Frontier is empty, stopping the crawler.")
                break

            url = self.frontier.pop()

            if (self.debug_code):
                print(f"\nVisiting {url}...")

            robots_txt = self.get_robots_txt(url)

            if not self.is_crawlable(url, robots_txt):
                continue

            url_normalized = self.normalize_url(url)

            if url_normalized is None or self.is_visited(url_normalized):
                continue

            #print(f"Normalized URL: {url_normalized}")

            fetch = self.fetch_url(url)

            if fetch is None:
                continue

            text, headers = fetch

            page = self.parser_content_to_html(url, text, headers)

            if page is None:
                continue

            domain = urlparse(url_normalized)
            
            if domain and domain.hostname:
                domain = domain.hostname

                if domain not in self.domain_count: # dominio novo, então continuo crawler
                    self.domain_count[domain] = 0
                    self.domain_count[domain] += 1
                else: # dominio já visitado - espero delay
                    
                    if self.domain_count[domain] > MAX_SAME_DOMAIN_VISITS:
                        if self.debug_code:
                            print(f"Domain {domain} has exceeded the limit, skipping.")
                        continue
                    
                    self.domain_count[domain] += 1 
                    delay = robots_txt.crawl_delay('*')

                    if delay:
                        if self.debug_code:
                            print(f"Delaying for {delay} seconds before crawling {url}.")
                            raise

                    time.sleep(float(delay) if delay else MIN_DELAY) # espero delay especificado no robots.txt ou então delay minimo 

            self.crawled_data.append((url, page, headers))

            self.len_crawled_data += 1

            links = self.extract_links(url_normalized, page)

            if links is not None:
                for link in links:
                    link_normalized = self.normalize_url(link)

                    if link_normalized is None or self.is_visited(link_normalized):
                        continue
                    
                    self.add_to_frontier_if_possible(link_normalized)

            self.visited_urls.add(url_normalized)

            block += 1
            
            if block >= NUMBER_OF_ENTRIES_IN_WARC_FILE:
                self.write_warc_and_gz(index_files)
                index_files += 1
                block = 0

            if self.debug_code:
                print(f"Total visited: {len(self.visited_urls)}")
        
        # write the visited pages in a json file
        with open('visited_urls.json', 'w') as f:
            json.dump(list(self.visited_urls), f, indent=4)
        
        print("Len of crawled data:", len(self.crawled_data))
        print("Visited URLs:", len(self.visited_urls))
        
        with open('domain_count.json', 'w') as f:
            json.dump(self.domain_count, f, indent=4) """

    def write_warc_and_gz(self, index: int) -> None:
        warc_filename = f"{CORPUS_OUTPUT_FOLDER}/corpus_{index}.warc"
        gz_filename = f"{warc_filename}.gz"

        # Write uncompressed WARC
        with open(warc_filename, "wb") as warc_file:
            writer = WARCWriter(warc_file, gzip=False)

            for url, html, headers in self.crawled_data:
                http_headers = StatusAndHeaders("200 OK", list(headers.items()), protocol="HTTP/1.0")

                record = writer.create_warc_record(
                    url,
                    "response",
                    payload=BytesIO(html.encode("utf-8")),
                    http_headers=http_headers
                )

                writer.write_record(record)

        # Compress the WARC to .gz
        with open(warc_filename, "rb") as f_in, gzip.open(gz_filename, "wb") as f_out:
            f_out.writelines(f_in)



    def normalize_url(self, url: str) -> str | None:

        try:
            
            normalized_url = url_normalize(url)
        
        except Exception as e:
            normalized_url = None

        if not normalized_url:
            if self.debug_code:
                print(f"Failed to normalize URL {url}, skipping.")
            return

        return normalized_url
    
    def add_to_frontier_if_possible(self, url: str) -> None:

        if url not in self.frontier:
            self.frontier.append(url)    

            if self.debug_code:
                print(f"Added {url} to frontier.")

        return 
    
    def is_visited(self, url: str) -> bool:
        
        if url in self.visited_urls:
            if self.debug_code:
                print(f"URL {url} already visited, skipping.")
            return True
        
        return False

    def is_crawlable(self, url: str, robots_txt: Protego | None) -> bool:
        
        if robots_txt is None:
            if self.debug_code:
                print(f"Robots.txt not found for {url}.")
            time.sleep(MIN_DELAY)
            return True
        
        if not robots_txt.can_fetch('*', url):
            if self.debug_code:
                print(f"Robots.txt disallows crawling {url}, skipping.")
            return False

        if url in self.visited_urls:
            if self.debug_code:
                print(f"URL {url} already visited, skipping.")
            return False
        
        return True


    def get_robots_txt(self, url: str) -> Protego | None:
        robots_txt_url = url + '/robots.txt'
        try:
            response = requests.get(robots_txt_url, timeout=TIMEOUT_LIMIT)
            if not response or not response.status_code == 200:
                if self.debug_code:
                    print(f"Failed to fetch robots.txt from {robots_txt_url}, skipping.")
                return None
            
            parser: Protego = Protego.parse(response.text)

            return parser
        
        except Exception as e:
            return None

    def fetch_url(self, url: str) -> tuple | None:
        try:
            response = requests.get(url, timeout=TIMEOUT_LIMIT)

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
            print(f"Request failed: {e}")
            return None

    def parser_content_to_html(self, url, text, headers) -> BeautifulSoup | None:

        page : BeautifulSoup = BeautifulSoup(text, 'html.parser')

        if not page:
            if self.debug_code:
                print(f"Failed to parse HTML for {url}, skipping.")
            return None
        
        if self.debug:
            title = page.title.string if page.title else "No title"
            text = page.get_text()
            text = ' '.join(text.split()[:20])
            timestamp = headers.get('Date', 'No date')
            timestamp_unix = int(datetime.strptime(timestamp, DATE_FORMAT).timestamp())

            print(DebugOutput(url, title, text, timestamp_unix))
        
        return page

    from urllib.parse import urljoin

    def extract_links(self, base_url: str, page: BeautifulSoup) -> list[str] | None:
        links = set(page.find_all('a', href=True))

        if not links:
            if self.debug_code:
                print(f"No links found in {base_url}, skipping.")
            return None

        filtered_links = []
        count_internal_links = 0

        for tag in links:
            href = tag['href']

            if not href or href.startswith(('mailto:', 'tel:', 'javascript:')):
                continue

            full_link = href if href.startswith('http') else urljoin(base_url, href)

            if full_link.startswith(base_url):
                if count_internal_links < MAX_SAME_DOMAIN_VISITS:
                    filtered_links.append(full_link)
                    count_internal_links += 1
                continue

            filtered_links.append(full_link)

        if self.debug_code:
            print(f"Filtered links: {filtered_links}")

        return filtered_links

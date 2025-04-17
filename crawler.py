from collections import deque
from bs4 import BeautifulSoup
import requests
from datetime import datetime
from debug_output import DebugOutput
from protego import Protego
import time
from url_normalize import url_normalize
from urllib.parse import urlparse
import json
import gzip
from io import BytesIO
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

DATE_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
MAX_SAME_DOMAIN_VISITS = 10 # max number of visits to the same domain
TIMEOUT_LIMIT = 5
CORPUS_OUTPUT_FOLDER = "corpus"

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

        for seed in seeds:
            self.frontier.append(seed)
            

    def init(self):

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

            if not self.is_crawlable(url):
                continue

            url_normalized = self.normalize_url(url)

            if url_normalized is None:
                continue

            print(f"Normalized URL: {url_normalized}")

            if self.is_visited(url_normalized):
                continue

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
                print(f"Domain: {domain}")
                if domain not in self.domain_count:
                    self.domain_count[domain] = 0
                self.domain_count[domain] += 1

                if self.domain_count[domain] > MAX_SAME_DOMAIN_VISITS:
                    if self.debug_code:
                        print(f"Domain {domain} has exceeded the limit, skipping.")
                    continue

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

            if block >= 10:
                self.write_warc_and_gz(index_files)
                index_files += 1
                block = 0
        
        # write the visited pages in a json file
        with open('visited_urls.txt', 'w') as f:
            json.dump(list(self.visited_urls), f)
                    
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

        normalized_url = url_normalize(url)
        
        if not normalized_url:
            if self.debug_code:
                print(f"Failed to normalize URL {url}, skipping.")
            return

        return normalized_url
    
    def add_to_frontier_if_possible(self, url: str) -> None:

        if url not in self.frontier:
            self.frontier.append(url)    

        return 
    
    def is_visited(self, url_normalized: str) -> bool:
        
        if url_normalized in self.visited_urls:
            if self.debug_code:
                print(f"URL {url_normalized} already visited, skipping.")
            return True
        
        return False

    def is_crawlable(self, url) -> bool:

        robots_txt : Protego = self.get_robots_txt(url)

        if robots_txt is None:
            if self.debug_code:
                print(f"Robots.txt not found for {url}.")
            time.sleep(0.1)
            return True

        if not robots_txt.can_fetch('*', url):
            if self.debug_code:
                print(f"Robots.txt disallows crawling {url}, skipping.")
            return False

        if url in self.visited_urls:
            if self.debug_code:
                print(f"URL {url} already visited, skipping.")
            return False
        
        delay = robots_txt.crawl_delay('*')

        time.sleep(float(delay) if delay else 0.1)
        
        return True


    def get_robots_txt(self, url: str) -> Protego | None:
        robots_txt_url = url + '/robots.txt'
        try:
            response = requests.get(robots_txt_url, timeout=TIMEOUT_LIMIT)
            if not response or not response.status_code == 200:
                return None
            
            parser: Protego = Protego.parse(response.text)

            return parser
        
        except requests.RequestException as e:
            return None

    def fetch_url(self, url: str) -> tuple[str, str] | None:
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
        
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            return None

    def parser_content_to_html(self, url, text, headers) -> BeautifulSoup | None:

        page : BeautifulSoup = BeautifulSoup(text, 'html.parser')

        if not page:
            return None
        
        if self.debug:
            title = page.title.string if page.title else "No title"
            text = page.get_text()
            text = ' '.join(text.split()[:20])
            timestamp = headers.get('Date', 'No date')
            timestamp_unix = int(datetime.strptime(timestamp, DATE_FORMAT).timestamp())

            print(DebugOutput(url, title, text, timestamp_unix))
        
        return page

    def extract_links(self, base_url: str,  page: BeautifulSoup) -> list[str] | None:

        # i am limiting the number of max internal links
        
        links = set(page.find_all('a', href=True))

        if not links:
            if self.debug_code:
                print(f"No links found in {base_url}, skipping.")
            return None

        #links = [link['href'] for link in links if link['href'] and link['href'].startswith('http')]

        filtered_links = []
        count_internal_links = 0 
        for link in links:
            
            if not link['href']:
                continue
            
            link = link['href']

            if not link.startswith('http'):
                continue
            
            if link.startswith(base_url):
                if count_internal_links < MAX_SAME_DOMAIN_VISITS:
                    filtered_links.append(link)
                    count_internal_links += 1
                continue

            filtered_links.append(link)
            
        return filtered_links
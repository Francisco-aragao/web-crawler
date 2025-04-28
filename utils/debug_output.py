class DebugOutput:

    """
        This class is just to help with debugging. It is used to print the crawl output in a readable format.
    """
    
    def __init__(self, url, title, text, timestamp):
        self.url : str = url
        self.title : str = title 
        self.text : str = text # 20 first words of the text
        self.timestamp : int = timestamp # unix time

    def __str__(self):
        return "{" + f" \"URL\": \"{self.url}\",\n\"Title\": \"{self.title}\",\n\"Text\": \"{' '.join(self.text.split()[:20])},\"\n\"Timestamp\": \"{self.timestamp}\"" + "}\n"
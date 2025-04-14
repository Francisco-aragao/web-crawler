class DebugOutput:
    def __init__(self, url, title, text, timestamp):
        self.url : str = url
        self.title : str = title 
        self.text : str = text # 20 first words of the text
        self.timestamp : int = timestamp # unix time

    def __str__(self):
        return f"URL: {self.url}\nTitle: {self.title}\nText: {' '.join(self.text.split()[:20])}\nTimestamp: {self.timestamp}\n"
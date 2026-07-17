class NewsItem:
    def __init__(self, id, publisher, title, author, published_utc, article_url, tickers, image_url, description, keywords):
        self.id = id
        self.publisher = publisher
        self.title = title
        self.author = author
        self.published_utc = published_utc
        self.article_url = article_url
        self.tickers = tickers
        self.image_url = image_url
        self.description = description
        self.keywords = keywords
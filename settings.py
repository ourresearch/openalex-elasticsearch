import os

ES_URL = os.environ.get("ES_URL_PROD", "http://elastic:testpass@127.0.0.1:9200")
WORKS_INDEX = "works-v15-*,-*invalid-data"

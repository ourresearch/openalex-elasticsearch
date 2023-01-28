import pandas as pd
from elasticsearch import Elasticsearch, helpers
from elasticsearch.helpers.errors import BulkIndexError

from settings import ES_URL


if __name__ == "__main__":
    es_client = Elasticsearch(ES_URL, timeout=30)
    chunk_size = 100000
    MERGE_AUTHORS_INDEX = "merge-authors"
    key = "https://openalex.org/A"
    count = 0
    AUTHORS_INDEX = "authors-v10"
    openalex_id = None

    for chunk in pd.read_csv("s3://openalex-sandbox/merge-away-authors-2022-01-19.csv.gz", chunksize=chunk_size):
        actions = []
        for index, row in chunk.iterrows():
            count = count + 1
            if count < 1200000:
                continue
            openalex_id = f"{key}{row[0]}"
            action = {
                "_id": openalex_id,
                "_op_type": "delete"
            }
            actions.append(action)

        print(f"Count is {count} with last deleted author id {openalex_id}")
        helpers.bulk(client=es_client, actions=actions, index=AUTHORS_INDEX, ignore_status=404)
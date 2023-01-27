import pandas as pd
from elasticsearch import Elasticsearch, helpers

from settings import ES_URL


if __name__ == "__main__":
    es_client = Elasticsearch(ES_URL)
    chunk_size = 100000
    MERGE_AUTHORS_INDEX = "merge-authors"
    key = "https://openalex.org/A"
    count = 0

    for chunk in pd.read_csv("s3://openalex-sandbox/merge-away-authors-2022-01-19.csv.gz", chunksize=chunk_size):
        document_list = []
        for index, row in chunk.iterrows():
            count = count + 1
            openalex_id = f"{key}{row[0]}"
            merge_into_id = "https://openalex.org/A4317838346"
            doc = {
                "id": openalex_id,
                "merge_into_id": merge_into_id,
            }
            document_list.append(doc)
        print(f"Count is {count}")
        helpers.bulk(es_client, document_list, index=MERGE_AUTHORS_INDEX)


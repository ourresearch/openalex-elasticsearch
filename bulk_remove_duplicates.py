import pandas as pd
from elasticsearch_dsl import Search, connections
from elasticsearch import ConflictError
from settings import ES_URL, WORKS_INDEX


def remove_duplicates():
    connections.create_connection(hosts=[ES_URL], timeout=30)
    chunk_size = 1000
    count = 0

    # loop run
    for chunk in pd.read_csv("s3://openalex-sandbox/work_ids_es_duplicates_20230619.txt", chunksize=chunk_size):
        for index, row in chunk.iterrows():
            count = count + 1
            openalex_id = f"https://openalex.org/W{row[0]}"
            if count > 2114000:
                find_id_and_delete(openalex_id)
        print(count)


def find_id_and_delete(id):
    s = Search(index=WORKS_INDEX)
    s = s.filter("term", id=id)
    s = s.sort("-@timestamp")
    response = s.execute()
    if s.count() == 2:
        record = response.hits[1]
        delete_from_elastic(record.id, record.meta.index)
    elif s.count() > 2:
        print(f"id {id} in elastic more than 2 times.")


def delete_from_elastic(duplicate_id, index):
    try:
        s = Search(index=index)
        s = s.filter("term", id=duplicate_id)
        s.delete()
        print(f"deleted duplicate id {duplicate_id} from index {index}")
    except ConflictError:
        print(f"conflict error while deleting duplicate id {duplicate_id} from index {index}")


if __name__ == "__main__":
    remove_duplicates()

import os
from datetime import datetime, timedelta

import backoff
from elasticsearch_dsl import Search, connections
from elasticsearch import ConflictError
import sentry_sdk
import requests
from settings import ES_URL, WORKS_INDEX

sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN"))

API_KEY = os.environ.get("API_KEY")


def remove_duplicates():
    """Removes duplicates coming from ingest into elasticsearch each hour."""
    start_time = datetime.utcnow()
    connections.create_connection(hosts=[ES_URL], timeout=30)

    duplicates = []

    three_hours_ago = (datetime.utcnow() - timedelta(hours=3)).isoformat()
    four_hours_ago = (datetime.utcnow() - timedelta(hours=4)).isoformat()

    per_page = 200

    # initial run
    cursor = "*"
    r = call_openalex_api(cursor, four_hours_ago, per_page, three_hours_ago)
    initial_count = r.json()["meta"]["count"]
    initial_ids = [work["id"] for work in r.json()["results"]]
    cursor = r.json()["meta"]["next_cursor"]

    s = Search(index=WORKS_INDEX)
    s = s.extra(size=2000)
    s = s.source(["id", "updated"])
    s = s.filter("terms", id=initial_ids)
    response = s.execute()
    elastic_ids = [r.id for r in response]

    for work_id in initial_ids:
        if elastic_ids.count(work_id) > 1:
            duplicates.append(work_id)
            find_id_and_delete(work_id)

    # loop run
    for i in range(1, int(initial_count / per_page)):
        print(f"loop {i} out of {int(initial_count / per_page)}")
        r = call_openalex_api(cursor, four_hours_ago, per_page, three_hours_ago)
        ids = [work["id"] for work in r.json()["results"]]
        cursor = r.json()["meta"]["next_cursor"]

        s = Search(index=WORKS_INDEX)
        s = s.extra(size=2000)
        s = s.source(["id", "updated"])
        s = s.filter("terms", id=ids)
        response = s.execute()
        elastic_ids = [r.id for r in response]

        for work_id in ids:
            if elastic_ids.count(work_id) > 1:
                duplicates.append(work_id)
                find_id_and_delete(work_id)

    end_time = datetime.utcnow()

    print(f"deleted {len(duplicates)} duplicates in {end_time - start_time}")


@backoff.on_exception(backoff.expo, (requests.exceptions.RequestException, requests.exceptions.JSONDecodeError), max_tries=5)
def call_openalex_api(cursor, four_hours_ago, per_page, three_hours_ago):
    url = f"https://api.openalex.org/works?filter=from_updated_date:{four_hours_ago},to_updated_date:{three_hours_ago}&api_key={API_KEY}&select=id&per-page={per_page}&cursor={cursor}"
    print(url)
    r = requests.get(url)
    return r


def find_id_and_delete(id):
    s = Search(index=WORKS_INDEX)
    s = s.filter("term", id=id)
    s = s.sort("-@timestamp")
    response = s.execute()
    if s.count() > 1:
        for record in response.hits[1:]:
            delete_from_elastic(record.id, record.meta.index)


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

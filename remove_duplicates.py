import os
from datetime import datetime, timedelta

from elasticsearch_dsl import Search, connections
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session

from models import Work
from settings import ES_URL, WORKS_INDEX


def remove_duplicates():
    engine = create_engine(os.getenv("DATABASE_URL"))
    session = Session(engine)
    connections.create_connection(hosts=[ES_URL], timeout=30)

    two_hours_ago = datetime.now() - timedelta(hours=2)
    three_hours_ago = two_hours_ago + timedelta(minutes=70)

    limit = 1
    offset = 1000
    max_records_to_process = 1000000

    for i in range(1, int(max_records_to_process / offset)):
        works_batch = (
            session.query(Work)
            .filter(Work.updated.between(three_hours_ago, two_hours_ago))
            .order_by(desc(Work.updated))
            .slice(limit, offset + 1)
            .all()
        )
        if not works_batch:
            # no more results
            break

        db_ids = [f"https://openalex.org/W{work.id}" for work in works_batch]

        s = Search(index=WORKS_INDEX)
        s = s.extra(size=2000)
        s = s.source(["id", "updated"])
        s = s.filter("terms", id=db_ids)
        response = s.execute()
        elastic_ids = [r.id for r in response]

        for work in works_batch:
            limit = limit + 1
            offset = offset + 1
            formatted_id = f"https://openalex.org/W{work.id}"
            if elastic_ids.count(formatted_id) > 1:
                find_id_and_delete(formatted_id)
        print(offset)


def find_id_and_delete(id):
    s = Search(index=WORKS_INDEX)
    s = s.filter("term", id=id)
    s = s.sort("-@timestamp")
    response = s.execute()
    if s.count() == 2:
        record = response.hits[1]
        delete_from_elastic(record.id, record.meta.index)


def delete_from_elastic(duplicate_id, index):
    s = Search(index=index)
    s = s.filter("term", id=duplicate_id)
    s.delete()
    print(f"deleted id {duplicate_id} from index {index}")


if __name__ == "__main__":
    remove_duplicates()

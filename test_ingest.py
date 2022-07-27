import os
from datetime import datetime, timedelta

from elasticsearch_dsl import Search, connections
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session

from models import Work
from settings import ES_URL, WORKS_INDEX


if __name__ == "__main__":
    engine = create_engine(os.getenv("DATABASE_URL"))
    session = Session(engine)
    connections.create_connection(hosts=[ES_URL], timeout=30)

    two_hours_ago = datetime.now() - timedelta(hours=2)
    one_day_ago = datetime.now() - timedelta(hours=26)

    limit = 1
    offset = 1000
    max_records_to_process = 1000000

    duplicates = []
    not_in_elastic = []
    mismatched_dates = []

    for i in range(1, int(max_records_to_process / offset)):
        works_batch = (
            session.query(Work)
            .filter(Work.updated.between(one_day_ago, two_hours_ago))
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
        elastic_dict = {r.id: r.updated for r in response}

        for work in works_batch:
            limit = limit + 1
            offset = offset + 1
            formatted_id = f"https://openalex.org/W{work.id}"
            if formatted_id not in elastic_ids:
                print(f"Work id {work.id} not in elasticsearch")
                not_in_elastic.append(work.id)
            elif elastic_ids.count(formatted_id) > 1:
                print(
                    f"Work id {work.id} has more than 1 record in elasticsearch. Count is {elastic_ids.count(formatted_id)}"
                )
                duplicates.append(
                    f"{work.id} (count {elastic_ids.count(formatted_id)})"
                )
            else:
                formatted_updated_db = str(work.updated)[:-3]
                formatted_updated_elastic = (
                    str(elastic_dict[formatted_id]).replace("T", " ").replace("Z", "")
                )
                if formatted_updated_elastic != formatted_updated_db:
                    mismatch_message = f"Work with id {work.id} has dates that do not match. DB: {formatted_updated_db}, Elastic: {formatted_updated_elastic}"
                    print(mismatch_message)
                    mismatched_dates.append(mismatch_message)
        print(offset)
    print(
        f"Summary: processed {offset} records.\nduplicates {duplicates}, not in elastic {not_in_elastic}, mismatched updated dates: {mismatched_dates}"
    )

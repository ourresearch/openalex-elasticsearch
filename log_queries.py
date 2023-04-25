# -*- coding: utf-8 -*-

DESCRIPTION = (
    """log the results of some queries to the `logs` schema in openalex-db (postgres)"""
)

import sys, os, time
from pathlib import Path
from datetime import datetime
from timeit import default_timer as timer

try:
    from humanfriendly import format_timespan
except ImportError:

    def format_timespan(seconds):
        return "{:.2f} seconds".format(seconds)


import logging

root_logger = logging.getLogger()
logger = root_logger.getChild(__name__)

import requests
from sqlalchemy import create_engine, desc, text
from sqlalchemy.orm import Session


def get_entity_count(entity: str) -> int:
    url = f"https://api.openalex.org/{entity}"
    r = requests.get(url)
    return r.json()["meta"]["count"]


def entity_counts_queries():
    timestamp = datetime.utcnow()
    counts = {}
    entities = [
        "works",
        "authors",
        "sources",
        "institutions",
        "publishers",
        "funders",
        "concepts",
    ]
    for entity in entities:
        counts[entity] = get_entity_count(entity)
    return {
        "timestamp": timestamp,
        "counts": counts,
    }


def query_count(query_url: str, session: Session, commit=True):
    if not 'select=' in query_url:
        query_url += 'select=id'
    if not 'mailto=' in query_url:
        query_url += 'mailto=dev@ourresearch.org'
    timestamp = datetime.utcnow()
    r = requests.get(query_url)
    num_results = r.json()["meta"]["count"]
    q = """
    INSERT INTO logs.count_queries
    (query_timestamp, num_results, query_url)
    VALUES(:query_timestamp, :num_results, :query_url)
    """
    params = {
        "query_timestamp": timestamp,
        "num_results": num_results,
        "query_url": query_url,
    }
    session.execute(text(q), params)
    if commit is True:
        session.commit()


def main(args):
    engine = create_engine(os.getenv("DATABASE_URL"))
    session = Session(engine)

    # entity counts queries
    q_results = entity_counts_queries()
    params = {
        "query_timestamp": q_results["timestamp"].isoformat(),
        "works": q_results["counts"]["works"],
        "authors": q_results["counts"]["authors"],
        "sources": q_results["counts"]["sources"],
        "institutions": q_results["counts"]["institutions"],
        "publishers": q_results["counts"]["publishers"],
        "funders": q_results["counts"]["funders"],
        "concepts": q_results["counts"]["concepts"],
    }
    session.execute(
        "INSERT INTO logs.entity_counts (query_timestamp, works, authors, sources, institutions, publishers, funders, concepts) VALUES(:query_timestamp, :works, :authors, :sources, :institutions, :publishers, :funders, :concepts)",
        params,
    )
    session.commit()

    # run arbitrary queries and get number of results, to store in logs.count_queries
    # TODO: this could replace entity counts queries above
    count_queries_to_run = [
        # entity counts
        "https://api.openalex.org/works",
        "https://api.openalex.org/authors",
        "https://api.openalex.org/sources",
        "https://api.openalex.org/institutions",
        "https://api.openalex.org/publishers",
        "https://api.openalex.org/funders",
        "https://api.openalex.org/concepts",
        # institution parsing
        "https://api.openalex.org/works?filter=authorships.institutions.id:null,has_doi:true",
        "https://api.openalex.org/works?filter=has_raw_affiliation_string:false,has_doi:true",
        "https://api.openalex.org/works?filter=has_raw_affiliation_string:true,authorships.institutions.id:null,has_doi:true&select=id,doi,authorships",
    ]
    for api_query in count_queries_to_run:
        query_count(api_query, session=session)

    session.close()


if __name__ == "__main__":
    total_start = timer()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(name)s.%(lineno)d %(levelname)s : %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    logger.info(" ".join(sys.argv))
    logger.info("{:%Y-%m-%d %H:%M:%S}".format(datetime.now()))
    logger.info("pid: {}".format(os.getpid()))
    import argparse

    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--debug", action="store_true", help="output debugging info")
    global args
    args = parser.parse_args()
    if args.debug:
        root_logger.setLevel(logging.DEBUG)
        logger.debug("debug mode is on")
    main(args)
    total_end = timer()
    logger.info(
        "all finished. total time: {}".format(format_timespan(total_end - total_start))
    )

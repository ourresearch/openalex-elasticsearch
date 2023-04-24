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
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session


def get_entity_count(entity: str) -> int:
    url = f"http://api.openalex.org/{entity}"
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


def main(args):
    engine = create_engine(os.getenv("DATABASE_URL"))
    session = Session(engine)
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

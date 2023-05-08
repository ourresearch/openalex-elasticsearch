# -*- coding: utf-8 -*-

DESCRIPTION = """Get the results from all simple groupby queries, then, for results that have fewer than 200 groups, save the possible values to elasticsearch"""

import sys, os, time
from pathlib import Path
from typing import List, Dict
from datetime import datetime
from timeit import default_timer as timer

try:
    from humanfriendly import format_timespan
except ImportError:

    def format_timespan(seconds):
        return "{:.2f} seconds".format(seconds)


import requests
from requests import JSONDecodeError
import backoff
from elasticsearch_dsl import Search, connections, Document, Text, Keyword, Object
from elasticsearch.exceptions import NotFoundError
from settings import ES_URL, GROUPBY_VALUES_INDEX

import logging

root_logger = logging.getLogger()
logger = root_logger.getChild(__name__)


class GroupbyValues(Document):
    # document for elasticsearch groupby_values index
    entity = Keyword()
    group_by = Keyword()
    values = Text()
    buckets = Object()

    class Index:
        name = GROUPBY_VALUES_INDEX


@backoff.on_predicate(backoff.expo, lambda x: x.status_code >= 429, max_tries=4)
def make_request(field, endpoint):
    r = requests.get(
        f"https://api.openalex.org/{endpoint}?group_by={field}&mailto=dev@ourresearch.org"
    )
    return r


def elasticsearch_save_or_update(
    entity: str, group_by: str, values: List[str], buckets: List[Dict[str, str]]
):
    # check if exists
    s = Search(index=GROUPBY_VALUES_INDEX)
    s = s.filter("term", entity=entity)
    s = s.filter("term", group_by=group_by)
    try:
        response = s.execute()
    except NotFoundError:
        response = []
    if len(response):
        # it exists. update the values
        record_id = response[0].meta.id
        g = GroupbyValues.get(record_id)
        g.update(values=values, buckets=buckets)
    else:
        # add a new record
        g = GroupbyValues(
            entity=entity, group_by=group_by, values=values, buckets=buckets
        )
        g.save()


def main(args):
    connections.create_connection(hosts=[ES_URL], timeout=30)
    i = 0
    # ignore_fields = [
    #     "has_fulltext",
    #     "has_raw_affiliation_string",
    # ]
    entities = [
        "works",
        "authors",
        "sources",
        "institutions",
        "concepts",
        "publishers",
        "funders",
    ]
    for entity in entities:
        errors = []
        errors_forbidden = []
        logger.info(f"ENTITY: {entity}")
        valid_fields = requests.get(
            f"https://api.openalex.org/{entity}/valid_fields"
        ).json()
        logger.info(f"{len(valid_fields)} valid_fields")
        num_saved_or_updated = 0
        for field in valid_fields:
            try:
                r = make_request(field, endpoint=entity)
                if r.status_code == 403:
                    errors_forbidden.append(f"entity: {entity}, field: {field}")
                    continue
                response = r.json()
                if "error" not in response and response["meta"]["count"] < 200:
                    values = [item["key"] for item in response["group_by"]]
                    # also save "buckets" which includes both the key and the key_display_name
                    buckets = [
                        {
                            "key": item["key"],
                            "key_display_name": item["key_display_name"],
                        }
                        for item in response["group_by"]
                    ]
                    # save to elasticsearch
                    elasticsearch_save_or_update(
                        entity=entity, group_by=field, values=values, buckets=buckets
                    )
                    num_saved_or_updated += 1
            except JSONDecodeError:
                errors.append(f"entity: {entity}, field: {field}")

        logger.info(
            f"finished {entity}. saved or updated {num_saved_or_updated} records in elasticsearch"
        )
        logger.info(f"ERRORS ENCOUNTERED -- FORBIDDEN: {errors_forbidden}")
        logger.info(f"ERRORS ENCOUNTERED -- UNKNOWN: {errors}")
        logger.info("----")


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

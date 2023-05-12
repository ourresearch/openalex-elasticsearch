# -*- coding: utf-8 -*-

DESCRIPTION = """For each publisher, get stats about how well their landing pages have been parsed, and save to openalex-db"""

import sys, os, time
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
from timeit import default_timer as timer

try:
    from humanfriendly import format_timespan
except ImportError:

    def format_timespan(seconds):
        return "{:.2f} seconds".format(seconds)


import requests
from requests import JSONDecodeError, RequestException
import backoff
from sqlalchemy import create_engine, desc, text
from sqlalchemy.orm import Session

import logging

root_logger = logging.getLogger()
logger = root_logger.getChild(__name__)

EMAIL = "dev@ourresearch.org"


def get_all_publishers(email=None):
    cursor = "*"

    endpoint = "publishers"

    select = [
        "id",
        "display_name",
        "works_count",
        "cited_by_count",
        "ids",
        "roles",
    ]
    params = {"select": ",".join(select)}

    # loop through pages
    publishers = []
    loop_index = 0
    logger.debug(f"getting all {endpoint}")
    while cursor:
        # set cursor value and request page from OpenAlex
        params["cursor"] = cursor
        url = f"https://api.openalex.org/{endpoint}"
        if email:
            params["mailto"] = email
        r = requests.get(url, params=params)
        page_with_results = r.json()
        if loop_index == 0:
            logger.debug(f"meta count property is {page_with_results['meta']['count']}")

        results = page_with_results["results"]
        publishers.extend(results)

        # update cursor to meta.next_cursor
        cursor = page_with_results["meta"]["next_cursor"]
        loop_index += 1
        if loop_index in [5, 10, 20, 50, 100] or loop_index % 500 == 0:
            logger.debug(f"{loop_index} api requests made so far")
    logger.debug(
        f"done. made {loop_index} api requests. collected {len(publishers)} works"
    )


def get_true_val_from_groupby(group_by: List[Dict]) -> int:
    if group_by:
        for gb in group_by:
            if gb["key"] == "true":
                return gb["count"]
    return -999


@backoff.on_exception(backoff.expo, RequestException, max_time=30)
@backoff.on_predicate(backoff.expo, lambda x: x.status_code >= 429, max_time=30)
def make_request(url, params):
    return requests.get(url, params=params)


def get_groupby_result(
    publisher_openalex_id: str,
    group_by: str,
    filters: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
) -> List[Dict]:
    # general method to get the groupby_results
    endpoint = "works"
    url = f"https://api.openalex.org/{endpoint}"
    if filters is None:
        filters = {}
    filters["primary_location.source.host_organization"] = publisher_openalex_id
    filters["has_doi"] = "true"
    params = {
        "filter": ",".join([f"{field}:{val}" for field, val in filters.items()]),
        "group_by": group_by,
    }
    if email:
        params["mailto"] = email
    try:
        r = make_request(url, params=params)
        return r.json()["group_by"]
    except (RequestException, JSONDecodeError, KeyError):
        logger.error(
            f"error when trying to make request with url {url} and params {params}"
        )
        logger.exception("message")
        return []


def get_groupby_true_count(
    publisher_openalex_id: str,
    group_by: str,
    filters: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
) -> int:
    # general method to get the true count from a groupby
    groupby_result = get_groupby_result(
        publisher_openalex_id, group_by, filters=filters, email=email
    )
    return get_true_val_from_groupby(groupby_result)


def get_data_one_publisher(
    publisher, timestamp_collection_start, email=None
) -> List[Dict[str, Any]]:
    pub_year_filter_vals = [
        ("<2015", "<2015"),
        (">=2015", ">2014"),
    ]  # first value is for display, second value is for the api filter
    publisher_openalex_id = publisher["id"]
    publisher_data = []
    for display_pub_year, pub_year_filter in pub_year_filter_vals:
        filters = {"publication_year": pub_year_filter}
        groupby_result = get_groupby_result(
            publisher_openalex_id, "type", filters=filters, email=email
        )
        for item in groupby_result:
            work_type = item["key"]
            count_this_type = item["count"]
            if count_this_type == 0:
                # has_raw_affiliation_string = 0
                # is_corresponding = 0
                # has_abstract = 0
                # has_pdf_url = 0
                continue
            else:
                filters["type"] = work_type
                has_raw_affiliation_string = get_groupby_true_count(
                    publisher_openalex_id,
                    "has_raw_affiliation_string",
                    filters=filters,
                    email=email,
                )
                is_corresponding = get_groupby_true_count(
                    publisher_openalex_id,
                    "is_corresponding",
                    filters=filters,
                    email=email,
                )
                has_abstract = get_groupby_true_count(
                    publisher_openalex_id, "has_abstract", filters=filters, email=email
                )
                has_pdf_url = get_groupby_true_count(
                    publisher_openalex_id, "has_pdf_url", filters=filters, email=email
                )
            publisher_data.append(
                {
                    "query_timestamp": datetime.utcnow().isoformat(),
                    "publisher_id": int(publisher_openalex_id.split("P")[-1]),
                    "publisher_display_name": publisher["display_name"],
                    "work_type": work_type,
                    "publication_year_range": display_pub_year,
                    "works_count": count_this_type,
                    "has_raw_affiliation": has_raw_affiliation_string,
                    "is_corresponding": is_corresponding,
                    "has_abstract": has_abstract,
                    "has_pdf_url": has_pdf_url,
                    "timestamp_collection_start": timestamp_collection_start,
                }
            )
    return publisher_data


def write_row_to_db(data_dict: Dict[str, Any], session: Session, commit=True):
    q = """
    INSERT INTO logs.landing_page_stats_by_publisher
    (query_timestamp, publisher_id, publisher_display_name, work_type, publication_year_range, works_count, has_raw_affiliation, is_corresponding, has_abstract, has_pdf_url, timestamp_collection_start)
    VALUES(:query_timestamp, :publisher_id, :publisher_display_name, :work_type, :publication_year_range, :works_count, :has_raw_affiliation, :is_corresponding, :has_abstract, :has_pdf_url, :timestamp_collection_start)
    """
    session.execute(text(q), data_dict)
    if commit is True:
        session.commit()


def main(args):
    timestamp_collection_start = datetime.utcnow()
    engine = create_engine(os.getenv("DATABASE_URL"))
    session = Session(engine)

    publishers = get_all_publishers(email=EMAIL)
    logger.info(
        f"there are {len(publishers)} publishers. Collecting stats for these publishers..."
    )

    for publisher in publishers:
        this_publisher_stats = get_data_one_publisher(
            publisher,
            timestamp_collection_start=timestamp_collection_start,
            email=EMAIL,
        )
        for row in this_publisher_stats:
            write_row_to_db(row, session, commit=False)
        session.commit()
        logger.debug(f"saved data to db for publisher {publisher['id']}")


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

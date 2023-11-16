# -*- coding: utf-8 -*-

DESCRIPTION = (
    """log the results of some queries to the `logs` schema in openalex-db (postgres)"""
)

import sys, os, time, json, csv
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
from requests import JSONDecodeError, RequestException
import backoff
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
        try:
            counts[entity] = get_entity_count(entity)
        except JSONDecodeError:
            logger.error(
                f"JSONDecodeError encountered when doing entity_counts_queries for entity {entity}"
            )
    return {
        "timestamp": timestamp,
        "counts": counts,
    }


def get_count_from_api(query_url: str) -> int:
    r = make_request(query_url)
    try:
        num_results = r.json()["meta"]["count"]
    except (RequestException, JSONDecodeError, KeyError, ValueError):
        logger.error(
            f"error when trying to make request with url {query_url}"
        )
        logger.exception("message")
        return -999
    return num_results


def query_count(query_url: str, session: Session, commit=True):
    # prepare the url
    if "select=" not in query_url:
        if "?" not in query_url:
            query_url += "?select=id"
        else:
            query_url += "&select=id"
    if "mailto=" not in query_url:
        query_url += "&mailto=dev@ourresearch.org"
    # get timestamp
    timestamp = datetime.utcnow()
    # make the request
    logger.debug(f"query_url: {query_url}")
    num_results = get_count_from_api(query_url)
    # insert into db
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


@backoff.on_exception(backoff.expo, RequestException, max_time=30)
@backoff.on_predicate(backoff.expo, lambda x: x.status_code >= 429, max_time=30)
def make_request(query_url, params=None):
    if params is None:
        r = requests.get(query_url)
    else:
        r = requests.get(query_url, params=params)
    return r

@backoff.on_exception(backoff.expo, RequestException, max_time=120)
@backoff.on_predicate(backoff.expo, lambda x: x.status_code >= 429, max_time=120)
def make_request_long_running(query_url, params=None):
    if params is None:
        r = requests.get(query_url)
    else:
        r = requests.get(query_url, params=params)
    return r


def get_institution_benchmarks(session: Session, commit=True):
    # get timestamp
    collection_start = datetime.utcnow()
    # get institution ids
    fp = Path("./institutions_for_scopus_compare.csv")
    if not fp.exists():
        logger.error(f"file does not exist: {fp}. skipping institution queries")
        return
    with fp.open('r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            institution_id = row['openalex_id']
            ror = row['ror']
            display_name = row['display_name']
            scopus_id = row['scopus_id']
            database = "openalex"
            query_timestamp = datetime.utcnow()
            # get data
            filters = f"institutions.id:{institution_id}"
            url = f"https://api.openalex.org/works?filter={filters}"
            num_works = get_count_from_api(url)

            filters = f"institutions.id:{institution_id},type:journal-article|article"
            url = f"https://api.openalex.org/works?filter={filters}"
            num_works_article_type = get_count_from_api(url)

            filters = f"institutions.id:{institution_id},has_doi:true"
            url = f"https://api.openalex.org/works?filter={filters}"
            num_works_has_doi = get_count_from_api(url)

            filters = f"institutions.id:{institution_id},is_oa:true"
            url = f"https://api.openalex.org/works?filter={filters}"
            num_works_open_access = get_count_from_api(url)


            # save to database
            q = """
            INSERT INTO logs.institution_scopus_compare
            (collection_start, institution_id, ror, display_name, scopus_id, num_works, num_works_article_type, num_works_has_doi, query_timestamp, "database", num_works_open_access)
            VALUES(:collection_start, :institution_id, :ror, :display_name, :scopus_id, :num_works, :num_works_article_type, :num_works_has_doi, :query_timestamp, :database, :num_works_open_access)
            """
            params = {
                "collection_start": collection_start,
                "institution_id": int(institution_id.split('I')[-1]),
                "ror": ror,
                "display_name": display_name,
                "scopus_id": scopus_id,
                "num_works": num_works,
                "num_works_article_type": num_works_article_type,
                "num_works_has_doi": num_works_has_doi,
                "query_timestamp": query_timestamp,
                "database": database,
                "num_works_open_access": num_works_open_access,
            }
            session.execute(text(q), params)
    if commit is True:
        session.commit()


def make_all_author_name_queries(session: Session, commit=True):
    # get timestamp
    timestamp = datetime.utcnow()
    # get author names
    fp = Path("./author_names.txt")
    if not fp.exists():
        logger.error(f"file does not exist: {fp}. skipping author name queries")
        return
    names = fp.read_text().split("\n")
    for name in names:
        query_url = (
            f"https://api.openalex.org/authors?search={name}&mailto=dev@ourresearch.org"
        )
        r = make_request(query_url)
        try:
            num_results = r.json()["meta"]["count"]
        except KeyError:
            logger.debug(r.status_code, r.text)
            continue
        except JSONDecodeError:
            logger.error(f"JSONDecodeError encountered when querying for name {name}")
            continue
        database = "openalex"
        # insert into db
        q = """
        INSERT INTO logs.author_names
        (query_timestamp, search_term, num_results, query_url, database)
        VALUES(:query_timestamp, :search_term, :num_results, :query_url, :database)
        """
        params = {
            "query_timestamp": timestamp,
            "search_term": name,
            "num_results": num_results,
            "query_url": query_url,
            "database": database,
        }
        session.execute(text(q), params)
    if commit is True:
        session.commit()


def query_groupby(query_url: str, session: Session, commit=True):
    # prepare the url
    if "mailto=" not in query_url:
        query_url += "&mailto=dev@ourresearch.org"
    # get timestamp
    timestamp = datetime.utcnow()
    # make the request
    logger.debug(f"query_url: {query_url}")
    r = make_request(query_url)
    if r.status_code == 403:
        return
    try:
        response = r.json()["group_by"]
    except KeyError:
        logger.error("KeyError")
        logger.error(r.status_code, r.text)
        return
    except JSONDecodeError:
        logger.error(f"JSONDecodeError encountered when running query {query_url}")
        return
    # insert into db
    q = """
    INSERT INTO logs.groupbys
    (query_timestamp, query_url, response)
    VALUES(:query_timestamp, :query_url, :response)
    """
    params = {
        "query_timestamp": timestamp,
        "query_url": query_url,
        "response": json.dumps(response),
    }
    session.execute(text(q), params)
    if commit is True:
        session.commit()
    return

def query_stats(query_url: str, session: Session, commit=True):
    # prepare the url
    if "mailto=" not in query_url:
        if "?" not in query_url:
            query_url += "?mailto=dev@ourresearch.org"
        else:
            query_url += "&mailto=dev@ourresearch.org"
    # get timestamp
    timestamp = datetime.utcnow()
    # make the request
    logger.debug(f"query_url: {query_url}")
    r = make_request_long_running(query_url)
    try:
        response = r.json()["stats"]
    except KeyError:
        logger.error("KeyError")
        logger.error(r.status_code, r.text)
        return
    except JSONDecodeError:
        logger.error(f"JSONDecodeError encountered when running query {query_url}")
        return
    # insert into db
    q = """
    INSERT INTO logs.stats_queries
    (query_timestamp, query_url, response)
    VALUES(:query_timestamp, :query_url, :response)
    """
    params = {
        "query_timestamp": timestamp,
        "query_url": query_url,
        "response": json.dumps(response),
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

    # make queries for author_name table
    make_all_author_name_queries(session=session)

    # make queries for institution_scopus_compare table
    get_institution_benchmarks(session=session)

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
        "https://api.openalex.org/works?filter=has_doi:true",
        "https://api.openalex.org/authors?filter=has_orcid:true",
        "https://api.openalex.org/works?filter=is_oa:true",
        "https://api.openalex.org/works?filter=has_references:true",
        "https://api.openalex.org/authors?filter=works_count:0",
        "https://api.openalex.org/authors?filter=works_count:1",
        "https://api.openalex.org/authors?filter=works_count:%3E5000",
        # institution parsing
        "https://api.openalex.org/works?filter=authorships.institutions.id:null,has_doi:true",
        "https://api.openalex.org/works?filter=has_raw_affiliation_string:false,has_doi:true",
        "https://api.openalex.org/works?filter=has_raw_affiliation_string:true,authorships.institutions.id:null,has_doi:true",
        "https://api.openalex.org/works?filter=open_access.is_oa:true,open_access.oa_status:closed",
    ]
    for api_query in count_queries_to_run:
        query_count(api_query, session=session)

    # groupby queries
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
        valid_fields = requests.get(
            f"https://api.openalex.org/{entity}/valid_fields"
        ).json()
        for field in valid_fields:
            url = f"https://api.openalex.org/{entity}?group_by={field}&mailto=dev@ourresearch.org"
            query_groupby(url, session=session)
    # filtered groupby queries
    filtered_groupby_queries_to_run = [
        "https://api.openalex.org/works?filter=open_access.is_oa:true&group_by=open_access.oa_status",
        "https://api.openalex.org/works?filter=open_access.is_oa:false&group_by=open_access.oa_status",
    ]
    for api_query in filtered_groupby_queries_to_run:
        query_groupby(api_query, session=session)

    stats_queries = [
        "https://api.openalex.org/works/stats/?filter=has_doi:true",
        "https://api.openalex.org/works/stats/",
    ]
    logger.debug(f"making stats queries ({len(stats_queries)} queries)")
    for api_query in stats_queries:
        query_stats(api_query, session=session)

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

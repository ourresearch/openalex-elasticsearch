# -*- coding: utf-8 -*-

DESCRIPTION = (
    """log the results of some queries to the `logs` schema in openalex-db (postgres)"""
)

import sys, os, time, json
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
from requests import JSONDecodeError
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
            logger.error(f"JSONDecodeError encountered when doing entity_counts_queries for entity {entity}")
    return {
        "timestamp": timestamp,
        "counts": counts,
    }


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
    r = requests.get(query_url)
    try:
        num_results = r.json()["meta"]["count"]
    except KeyError:
        logger.debug(r.status_code, r.text)
    except JSONDecodeError:
        logger.error(f"JSONDecodeError encountered when running query {query_url}")
        return
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


def query_groupby(query_url: str, session: Session, commit=True):
    # prepare the url
    if "mailto=" not in query_url:
        query_url += "&mailto=dev@ourresearch.org"
    # get timestamp
    timestamp = datetime.utcnow()
    # make the request
    logger.debug(f"query_url: {query_url}")
    r = requests.get(query_url)
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
    ]
    for api_query in count_queries_to_run:
        query_count(api_query, session=session)

    # groupby queries
    groupby_queries = [
        "https://api.openalex.org/works?group_by=alternate_host_venues.id",
        "https://api.openalex.org/works?group_by=alternate_host_venues.license",
        "https://api.openalex.org/works?group_by=alternate_host_venues.version",
        "https://api.openalex.org/works?group_by=author.id",
        "https://api.openalex.org/works?group_by=author.orcid",
        "https://api.openalex.org/works?group_by=authors_count",
        "https://api.openalex.org/works?group_by=authorships.author.id",
        "https://api.openalex.org/works?group_by=authorships.author.orcid",
        "https://api.openalex.org/works?group_by=authorships.institutions.continent",
        "https://api.openalex.org/works?group_by=authorships.institutions.country_code",
        "https://api.openalex.org/works?group_by=authorships.institutions.id",
        "https://api.openalex.org/works?group_by=authorships.institutions.is_global_south",
        "https://api.openalex.org/works?group_by=authorships.institutions.ror",
        "https://api.openalex.org/works?group_by=authorships.institutions.type",
        "https://api.openalex.org/works?group_by=authorships.is_corresponding",
        "https://api.openalex.org/works?group_by=best_oa_location.is_oa",
        "https://api.openalex.org/works?group_by=best_oa_location.license",
        "https://api.openalex.org/works?group_by=best_oa_location.source.host_organization",
        "https://api.openalex.org/works?group_by=best_oa_location.source.host_organization_lineage",
        "https://api.openalex.org/works?group_by=best_oa_location.source.id",
        "https://api.openalex.org/works?group_by=best_oa_location.source.issn",
        "https://api.openalex.org/works?group_by=best_oa_location.source.type",
        "https://api.openalex.org/works?group_by=best_oa_location.venue.issn",
        "https://api.openalex.org/works?group_by=best_oa_location.venue.type",
        "https://api.openalex.org/works?group_by=best_oa_location.version",
        "https://api.openalex.org/works?group_by=best_open_version",
        "https://api.openalex.org/works?group_by=cited_by_count",
        "https://api.openalex.org/works?group_by=cites",
        "https://api.openalex.org/works?group_by=concept.id",
        "https://api.openalex.org/works?group_by=concepts.id",
        "https://api.openalex.org/works?group_by=concepts.wikidata",
        "https://api.openalex.org/works?group_by=concepts_count",
        "https://api.openalex.org/works?group_by=corresponding_author_ids",
        "https://api.openalex.org/works?group_by=corresponding_institution_ids",
        "https://api.openalex.org/works?group_by=doi_starts_with",
        "https://api.openalex.org/works?group_by=grants.award_id",
        "https://api.openalex.org/works?group_by=grants.funder",
        "https://api.openalex.org/works?group_by=has_abstract",
        "https://api.openalex.org/works?group_by=has_doi",
        "https://api.openalex.org/works?group_by=has_ngrams",
        "https://api.openalex.org/works?group_by=has_oa_accepted_or_published_version",
        "https://api.openalex.org/works?group_by=has_oa_submitted_version",
        "https://api.openalex.org/works?group_by=has_orcid",
        "https://api.openalex.org/works?group_by=has_pmcid",
        "https://api.openalex.org/works?group_by=has_pmid",
        "https://api.openalex.org/works?group_by=has_references",
        "https://api.openalex.org/works?group_by=host_venue.display_name",
        "https://api.openalex.org/works?group_by=host_venue.id",
        "https://api.openalex.org/works?group_by=host_venue.issn",
        "https://api.openalex.org/works?group_by=host_venue.license",
        "https://api.openalex.org/works?group_by=host_venue.publisher",
        "https://api.openalex.org/works?group_by=host_venue.type",
        "https://api.openalex.org/works?group_by=host_venue.version",
        "https://api.openalex.org/works?group_by=ids.openalex",
        "https://api.openalex.org/works?group_by=institution.id",
        "https://api.openalex.org/works?group_by=institutions.continent",
        "https://api.openalex.org/works?group_by=institutions.country_code",
        "https://api.openalex.org/works?group_by=institutions.id",
        "https://api.openalex.org/works?group_by=institutions.is_global_south",
        "https://api.openalex.org/works?group_by=institutions.ror",
        "https://api.openalex.org/works?group_by=institutions.type",
        "https://api.openalex.org/works?group_by=is_corresponding",
        "https://api.openalex.org/works?group_by=is_oa",
        "https://api.openalex.org/works?group_by=is_paratext",
        "https://api.openalex.org/works?group_by=is_retracted",
        "https://api.openalex.org/works?group_by=journal",
        "https://api.openalex.org/works?group_by=locations.is_oa",
        "https://api.openalex.org/works?group_by=locations.license",
        "https://api.openalex.org/works?group_by=locations.source.host_institution_lineage",
        "https://api.openalex.org/works?group_by=locations.source.host_organization",
        "https://api.openalex.org/works?group_by=locations.source.host_organization_lineage",
        "https://api.openalex.org/works?group_by=locations.source.id",
        "https://api.openalex.org/works?group_by=locations.source.issn",
        "https://api.openalex.org/works?group_by=locations.source.publisher_lineage",
        "https://api.openalex.org/works?group_by=locations.source.type",
        "https://api.openalex.org/works?group_by=locations.venue.issn",
        "https://api.openalex.org/works?group_by=locations.venue.type",
        "https://api.openalex.org/works?group_by=locations.version",
        "https://api.openalex.org/works?group_by=oa_status",
        "https://api.openalex.org/works?group_by=open_access.any_repository_has_fulltext",
        "https://api.openalex.org/works?group_by=open_access.is_oa",
        "https://api.openalex.org/works?group_by=open_access.oa_status",
        "https://api.openalex.org/works?group_by=openalex",
        "https://api.openalex.org/works?group_by=openalex_id",
        "https://api.openalex.org/works?group_by=primary_location.is_oa",
        "https://api.openalex.org/works?group_by=primary_location.license",
        "https://api.openalex.org/works?group_by=primary_location.source.has_issn",
        "https://api.openalex.org/works?group_by=primary_location.source.host_organization",
        "https://api.openalex.org/works?group_by=primary_location.source.host_organization_lineage",
        "https://api.openalex.org/works?group_by=primary_location.source.id",
        "https://api.openalex.org/works?group_by=primary_location.source.issn",
        "https://api.openalex.org/works?group_by=primary_location.source.type",
        "https://api.openalex.org/works?group_by=primary_location.venue.has_issn",
        "https://api.openalex.org/works?group_by=primary_location.version",
        "https://api.openalex.org/works?group_by=publication_year",
        "https://api.openalex.org/works?group_by=repository",
        "https://api.openalex.org/works?group_by=type",
        "https://api.openalex.org/works?group_by=version",
        "https://api.openalex.org/authors?group_by=cited_by_count",
        "https://api.openalex.org/authors?group_by=concept.id",
        "https://api.openalex.org/authors?group_by=concepts.id",
        "https://api.openalex.org/authors?group_by=has_orcid",
        "https://api.openalex.org/authors?group_by=last_known_institution.continent",
        "https://api.openalex.org/authors?group_by=last_known_institution.country_code",
        "https://api.openalex.org/authors?group_by=last_known_institution.id",
        "https://api.openalex.org/authors?group_by=last_known_institution.is_global_south",
        "https://api.openalex.org/authors?group_by=last_known_institution.ror",
        "https://api.openalex.org/authors?group_by=last_known_institution.type",
        "https://api.openalex.org/authors?group_by=openalex",
        "https://api.openalex.org/authors?group_by=openalex_id",
        "https://api.openalex.org/authors?group_by=orcid",
        "https://api.openalex.org/authors?group_by=summary_stats.2yr_mean_citedness",
        "https://api.openalex.org/authors?group_by=summary_stats.h_index",
        "https://api.openalex.org/authors?group_by=summary_stats.i10_index",
        "https://api.openalex.org/authors?group_by=works_count",
        "https://api.openalex.org/authors?group_by=x_concepts.id",
        "https://api.openalex.org/sources?group_by=apc_prices.currency",
        "https://api.openalex.org/sources?group_by=apc_prices.price",
        "https://api.openalex.org/sources?group_by=apc_usd",
        "https://api.openalex.org/sources?group_by=cited_by_count",
        "https://api.openalex.org/sources?group_by=concept.id",
        "https://api.openalex.org/sources?group_by=concepts.id",
        "https://api.openalex.org/sources?group_by=continent",
        "https://api.openalex.org/sources?group_by=country_code",
        "https://api.openalex.org/sources?group_by=has_issn",
        "https://api.openalex.org/sources?group_by=host_organization",
        "https://api.openalex.org/sources?group_by=host_organization.id",
        "https://api.openalex.org/sources?group_by=host_organization_lineage",
        "https://api.openalex.org/sources?group_by=ids.openalex",
        "https://api.openalex.org/sources?group_by=is_global_south",
        "https://api.openalex.org/sources?group_by=is_in_doaj",
        "https://api.openalex.org/sources?group_by=is_oa",
        "https://api.openalex.org/sources?group_by=issn",
        "https://api.openalex.org/sources?group_by=openalex",
        "https://api.openalex.org/sources?group_by=openalex_id",
        "https://api.openalex.org/sources?group_by=publisher",
        "https://api.openalex.org/sources?group_by=summary_stats.2yr_mean_citedness",
        "https://api.openalex.org/sources?group_by=summary_stats.h_index",
        "https://api.openalex.org/sources?group_by=summary_stats.i10_index",
        "https://api.openalex.org/sources?group_by=type",
        "https://api.openalex.org/sources?group_by=works_count",
        "https://api.openalex.org/sources?group_by=x_concepts.id",
        "https://api.openalex.org/institutions?group_by=cited_by_count",
        "https://api.openalex.org/institutions?group_by=concept.id",
        "https://api.openalex.org/institutions?group_by=concepts.id",
        "https://api.openalex.org/institutions?group_by=continent",
        "https://api.openalex.org/institutions?group_by=country_code",
        "https://api.openalex.org/institutions?group_by=has_ror",
        "https://api.openalex.org/institutions?group_by=is_global_south",
        "https://api.openalex.org/institutions?group_by=openalex",
        "https://api.openalex.org/institutions?group_by=openalex_id",
        "https://api.openalex.org/institutions?group_by=repositories.host_organization",
        "https://api.openalex.org/institutions?group_by=repositories.host_organization_lineage",
        "https://api.openalex.org/institutions?group_by=repositories.id",
        "https://api.openalex.org/institutions?group_by=ror",
        "https://api.openalex.org/institutions?group_by=summary_stats.2yr_mean_citedness",
        "https://api.openalex.org/institutions?group_by=summary_stats.h_index",
        "https://api.openalex.org/institutions?group_by=summary_stats.i10_index",
        "https://api.openalex.org/institutions?group_by=type",
        "https://api.openalex.org/institutions?group_by=works_count",
        "https://api.openalex.org/institutions?group_by=x_concepts.id",
        "https://api.openalex.org/concepts?group_by=ancestors.id",
        "https://api.openalex.org/concepts?group_by=cited_by_count",
        "https://api.openalex.org/concepts?group_by=has_wikidata",
        "https://api.openalex.org/concepts?group_by=level",
        "https://api.openalex.org/concepts?group_by=openalex",
        "https://api.openalex.org/concepts?group_by=openalex_id",
        "https://api.openalex.org/concepts?group_by=summary_stats.2yr_mean_citedness",
        "https://api.openalex.org/concepts?group_by=summary_stats.h_index",
        "https://api.openalex.org/concepts?group_by=summary_stats.i10_index",
        "https://api.openalex.org/concepts?group_by=wikidata_id",
        "https://api.openalex.org/concepts?group_by=works_count",
        "https://api.openalex.org/publishers?group_by=cited_by_count",
        "https://api.openalex.org/publishers?group_by=continent",
        "https://api.openalex.org/publishers?group_by=country_codes",
        "https://api.openalex.org/publishers?group_by=hierarchy_level",
        "https://api.openalex.org/publishers?group_by=ids.openalex",
        "https://api.openalex.org/publishers?group_by=ids.ror",
        "https://api.openalex.org/publishers?group_by=ids.wikidata",
        "https://api.openalex.org/publishers?group_by=lineage",
        "https://api.openalex.org/publishers?group_by=openalex",
        "https://api.openalex.org/publishers?group_by=parent_publisher",
        "https://api.openalex.org/publishers?group_by=ror",
        "https://api.openalex.org/publishers?group_by=summary_stats.2yr_mean_citedness",
        "https://api.openalex.org/publishers?group_by=summary_stats.h_index",
        "https://api.openalex.org/publishers?group_by=summary_stats.i10_index",
        "https://api.openalex.org/publishers?group_by=wikidata",
        "https://api.openalex.org/publishers?group_by=works_count",
        "https://api.openalex.org/funders?group_by=cited_by_count",
        "https://api.openalex.org/funders?group_by=continent",
        "https://api.openalex.org/funders?group_by=country_code",
        "https://api.openalex.org/funders?group_by=ids.openalex",
        "https://api.openalex.org/funders?group_by=ids.ror",
        "https://api.openalex.org/funders?group_by=ids.wikidata",
        "https://api.openalex.org/funders?group_by=is_global_south",
        "https://api.openalex.org/funders?group_by=openalex",
        "https://api.openalex.org/funders?group_by=ror",
        "https://api.openalex.org/funders?group_by=summary_stats.2yr_mean_citedness",
        "https://api.openalex.org/funders?group_by=summary_stats.h_index",
        "https://api.openalex.org/funders?group_by=summary_stats.i10_index",
        "https://api.openalex.org/funders?group_by=wikidata",
        "https://api.openalex.org/funders?group_by=works_count",
    ]
    for api_query in groupby_queries:
        query_groupby(api_query, session=session)

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

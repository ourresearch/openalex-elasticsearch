# Example queries

##### Count of all the open-access articles in this journal, year-by-year

`/query?filter=issn:2167-8359&is_open=true&groupby=year`

```
GET works-*/_search?request_cache=false
{
	"size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "journal.all_issns": "2167-8359"
          }
        },
        {
          "term": {
            "unpaywall.is_oa_bool": true
          }
        }
      ]
    }
  },
  "aggs": {
    "by_year": {
      "terms": {
        "field": "year",
        "size": 10
      }
    }
  }
}
```

##### See which journals are publishing the kangaroo-themed articles that australian authors write

`query?title=”kangaroo”&country_code=AUS&group_by=issn`

```
GET works-*/_search?request_cache=false
{
  "size": 0,
   "query": {
    "bool": {
      "must": [
        {
          "bool": {
            "must": [
              {
                "nested": {
                  "path": "affiliations",
                  "query": {
                    "bool": {
                      "should": [
                        {
                          "match_phrase": {
                            "affiliations.country_code": "au"
                          }
                        }
                      ]
                    }
                  }
                }
              },
              {
                "bool": {
                  "should": [
                    {
                      "match": {
                        "work_title": "kangaroos"
                      }
                    }
                  ]
                }
              }
            ]
          }
        }
      ]
    }
  },
   "aggs": {
      "by_issn": {
        "terms": {
          "field": "journal.all_issns",
          "size": 50
        }
      }
  }
}
```

##### See how many papers have been written since 2010 by each author affiliated with the University of Florida

`query?filter=year>2010&ror_id=02y3ad647&group_by=author_id`

```
GET works-*/_search?request_cache=false
{
  "size": 0,
   "query": {
    "bool": {
      "must": [
        {
          "bool": {
            "must": [
              {
                "bool": {
                  "must": [
                    {
                      "range": {
                        "year": {
                          "gt": "2010"
                        }
                      }
                    }
                  ]
                }
              },
              {
                "nested": {
                  "path": "affiliations",
                  "query": {
                    "bool": {
                      "must": [
                        {
                          "term": {
                            "affiliations.ror": "02y3ad647"
                          }
                        }
                      ]
                    }
                  }
                }
              }
            ]
          }
        }
      ]
    }
  },
   "aggs": {
    "group_by_author": {
        "nested": {
          "path": "affiliations"
        },
        "aggs": {
          "author_id": {
            "terms": {
              "field": "affiliations.author_id"
            }
          }
        }
      }
  }
}
```
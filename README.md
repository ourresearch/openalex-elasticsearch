# OpenAlex Elasticsearch

This repository contains the Elasticsearch template and Logstash configuration that supports 
the OpenAlex API.

### Overview

Records in OpenAlex are academic articles known as _works_. Each work includes fields 
such as work title, journal title, author information, and publication date.

Works start out in AWS Redshift. We use Logstash deployed as a docker instance on Digital Ocean to pull the records 
from Redshift into Elasticsearch.

### Elasticsearch Architecture

Works documents are stored in indeces grouped by publication year, with a goal to hold 1 to 20 million records
(5gb to 40gb) in each index shard. After consolidating everything from 1959 and older into a single index, we
expect to have around 50 indeces to start.

Due to an expected low ingest rate of around 50k records per day, each index 
is set with:

- 1 primary shard
- 1 replica shard

The current Elasticsearch cluster is 2 nodes which is expected to grow to 4 nodes in production. With 4 nodes we will 
expand to:

- 1 primary shard
- 3 replica shards

for each index, and plan to add more replicas as we add additional nodes to support traffic.

#### Elasticsearch Index Template

The template is located [here](/elasticsearch_templates/works_template.json). Example queries are [here](/elasticsearch_templates/queries.md).

### Logstash setup

Logstash is deployed on a Digital Ocean droplet called openalex-logstash. 

Start the app:
1. Open the openalex-logstash droplet control panel in Digital Ocean
2. Click Console to open a unix terminal
3. In the terminal window, browse to the app directory with: `cd /mnt/logstash_volume/logstash`
4. Run the service with `docker-compose up -d`

Stop the app:
1. Browse to the app directory with: `cd /mnt/logstash_volume/logstash`
2. Run `docker-compose stop`

Please send all bug reports and feature requests to support@openalex.org.

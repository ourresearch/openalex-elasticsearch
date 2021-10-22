FROM docker.elastic.co/logstash/logstash:7.15.1
RUN rm -f /usr/share/logstash/pipeline/logstash.conf
COPY load/ /usr/share/logstash/pipeline/
COPY jars/. /usr/share/logstash/logstash-core/lib/jars
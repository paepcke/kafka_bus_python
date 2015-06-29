#!/usr/bin/env bash

# Delete given topic from Kafka. Only works with Kafka running locally.
# Assume that $KAFKA_ROOT points to local server's Kafka installation
# root (i.e. bin is one of $KAFKA_ROOT's subdirectories).

if [[ $# != 1 ]]
then
    echo "Usage: deleteTopic.sh <topicName>"
    exit -1
fi

cd $KAFKA_ROOT
bin/kafka-topics.sh --zookeeper localhost:2181/ --delete --topic $1

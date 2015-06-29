#!/usr/bin/env bash

# List topics on Kafka. Only works with Kafka running locally.
# Assume that $KAFKA_ROOT points to local server's Kafka installation
# root (i.e. bin is one of $KAFKA_ROOT's subdirectories).

cd $KAFKA_ROOT
bin/kafka-topics.sh --zookeeper localhost:2181/ --list

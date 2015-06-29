#!/usr/bin/env python

'''

Create 10,000 topics T0-T99999 in a loop.
(Very slow).

Created on Jun 29, 2015

@author: paepcke
'''

from datetime import datetime
import logging

from kafka_bus_python.kafka_bus import BusAdapter


if __name__ == '__main__':
    bus = BusAdapter(loggingLevel=logging.ERROR)
    print("%s: Starting 10,000 new topics." % datetime.now().isoformat())
    for i in range(10000):
        bus.subscribeToTopic('T%s' % str(i))
    print("%s: Done creating 10,000 new topics." % datetime.now().isoformat())
    

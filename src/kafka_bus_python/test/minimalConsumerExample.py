'''
Created on Jun 29, 2015

@author: paepcke
'''
import time

from kafka_bus_python.kafka_bus import BusAdapter

def printMessage(topicName, msgText, msgOffset):
    print('Msg[%s]: %s' % (topicName, msgText))

bus = BusAdapter()
bus.subscribeToTopic('exampleTopic', printMessage)

while True:
    # do anything you like
    time.sleep(10)

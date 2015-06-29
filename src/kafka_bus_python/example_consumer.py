#!/usr/bin/env python

'''
Created on May 22, 2015

@author: paepcke
'''

import functools
import sys
import time

from kafka_bus import BusAdapter


class BusModuleConsumer(object):
    '''
    Example for a bus module that subscribes to a 
    topic, and then echoes all messages to the screen.
    '''
    
    DEFAULT_TOPIC = 'example_use'

    def __init__(self, topicName=None):
        '''
        Create a BusAdapter, subscribe to topic 'example_use',
        passing a function that takes parameters topicName, msgText, and msgOffset
        Then sleep over and over again, getting callbacks whenever
        a message arrives. 
        '''
        if topicName is None:
            self.topicName = BusModuleConsumer.DEFAULT_TOPIC
        else:
            self.topicName = topicName
        
        # The following statement is needed only 
        # if your callback is a *method* (rather than a top 
        # level function). That's because Python methods
        # take 'self' as a first argument, while the Bus 
        # expects a function that just takes topicName, msgText, and msgOffset.
        # The following statement creates a function wrapper around 
        # our callback method that has the leading 'self' parameter built 
        # in. The process is called function currying. If
        # printMessage() were a top level function, we would 
        # simply pass printMessage to the subscribeToTopic() call
        # below:
        
        self.exampleDeliveryMethod = functools.partial(self.printMessage)        
        
        # Create a BusAdapter instance, telling it that its
        # server(s) are on machine mono.stanford.edu:
        
        bus = BusAdapter()

        # Tell the bus that you are interested in the topic self.topicName,
        # and want callbacks to self.exampleDeliveryMethod whenever
        # a message arrives:
        
        bus.subscribeToTopic(self.topicName, self.exampleDeliveryMethod)
        
        # Now we do nothing. In a production system you 
        # would do something useful here:
        
        while True:
            # do anything you like
            time.sleep(10)

    def printMessage(self, topicName, msgText, msgOffset):
        '''
        This method is called whenever a message in topic
        self.topicName is published by anyone on the bus.
        It just prints the message topic and content.
        
        :param topicName: name of topic to which the arriving msg belongs
        :type topicName: string
        :param msgText: text part of the message. Could be JSON, or anything else. 
        :type msgText: string
        :param msgOffset: position of message in the topic's message history
        :type msgOffset: int
        '''
        print('Msg[%s]: %s' % (topicName, msgText))


if __name__ == '__main__':
    
    if (len(sys.argv) > 1):
        arg = sys.argv[1]
        if arg == '-h' or arg == '--help':
            print('Usage: example_consumer.py [topicName]')
            sys.exit()
        else:
            print("Begin listening to topic '%s'..." % arg)
            BusModuleConsumer(topicName=arg)
    else:
        print("Begin listening to topic '%s'..." % BusModuleConsumer.DEFAULT_TOPIC)
        BusModuleConsumer()
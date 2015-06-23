#!/usr/bin/env python

'''
Created on May 22, 2015

@author: paepcke
'''

import kafka

from kafka_bus import BusAdapter


class BusModuleProducer(object):
    '''
    Example for a bus module that publishes messages
    to topic 'example_use'.
    '''

    def __init__(self):
        '''
        In a loop: ask for message text from command line,
        and publish to topic 'example_use'.
        '''

        # Create a BusAdapter instance, telling it that its
        # server(s) are on machine mono.stanford.edu:

        bus = BusAdapter(kafkaHost='mono.stanford.edu')

        while True:
            # Read one line from console:
            msgText = raw_input("Type a message to send: ('Q' to end.): ")
            if msgText == 'Q':
                break
            else:
                #*********
                # bus.publish(msgText, 'example_use')
                try:
                    bus.publish(msgText, 'example_use')
                except kafka.common.FailedPayloadsError as e:
                    print("Got payload error, retrying... (%s)" % `e`)
                    try:
                        bus.publish(msgText, 'example_use')
                    except kafka.common.FailedPayloadsError as e:
                        print("Got payload error again (%s)" % `e`)
                        continue
                #*********
if __name__ == '__main__':
    BusModuleProducer()

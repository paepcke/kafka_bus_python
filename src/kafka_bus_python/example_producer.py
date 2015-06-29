#!/usr/bin/env python

'''
Created on May 22, 2015

@author: paepcke
'''

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
        self.bus = BusAdapter(kafkaHost='mono.stanford.edu')
        self.sendMessages()
        
    def sendMessages(self):
        '''
        In a loop, ask for message to send, and send it. 
        '''

        while True:
            # Read one line from console:
            msgText = raw_input("Type a message to send: ('Q' to end.): ")
            if msgText == 'Q':
                break
            else:
                self.bus.publish(msgText, 'example_use')

if __name__ == '__main__':
    BusModuleProducer()        
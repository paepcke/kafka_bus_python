'''
Created on May 19, 2015

@author: paepcke
'''
import threading

from kafka import SimpleConsumer


class TopicWaiter(threading.Thread):
    '''
    classdocs
    '''


    def __init__(self, topicName, busModule, deliveryCallback=None):
        '''
        Constructor
        '''        
        threading.Thread.__init__(self)
        self.topicName = topicName
        self.busModule = busModule
        if deliveryCallback is None:
            self.deliveryCallback = deliveryCallback 
        else:
            self.deliveryCallback = busModule.resultCallback
        self.done = False
        self.run()

    def run(self):
        # Consumer prints out all events logged by any producer. Times out in 3 minutes.
        while not self.done:
            topicMsgs = SimpleConsumer(self.busModule.kafkaClient, group=None, topic=self.topicName, iter_timeout=180)
            for topicMsg in topicMsgs:
                self.deliveryCallback(topicMsg.value.decode('UTF-8'))
                if self.done:
                    break
        
    def stop(self):
        self.done = True
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
            self.deliveryCallbacks = [deliveryCallback] 
        else:
            self.deliveryCallbacks = [busModule.resultCallback]
        self.done = False
        self.run()

    def addListener(self, callback):
        '''
        Add a listener who will be notified with any
        message that arrives on the topic.
        
        :param callback: function with two args: a topic name, and
            a string that is the message content.
        :type callback: function 
        '''
        self.deliveryCallbacks.append(callback)

    def removeListener(self, callback):
        try:
            self.deliveryCallbacks.remove(callback)
        except ValueError:
            # This callback func wasn't registered
            # in the first place:
            return

    def listeners(self):
        return self.deliveryCallbacks

    def run(self):
        # Consumer prints out all events logged by any producer. Times out in 3 minutes.
        while not self.done:
            topicMsgs = SimpleConsumer(self.busModule.kafkaClient, group=None, topic=self.topicName, iter_timeout=180)
            for topicMsg in topicMsgs:
                cleanMsgContent = topicMsg.value.decode('UTF-8')
                for deliveryFunc in self.deliveryCallbacks:
                    deliveryFunc(cleanMsgContent)
                    if self.done:
                        break
                if self.done:
                    break
        
    def stop(self):
        self.done = True
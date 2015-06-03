'''
Created on May 22, 2015

@author: paepcke
'''

import functools
import json
import threading

from kafka_bus_python.kafka_bus import BusAdapter


class EchoServer(threading.Thread):
    '''
    Producer thread. Can be called with the following
    characteristics:
        o Send a msg once
        o Before sending any (one or cyclically) more msgs only after method setTrigger() was called.
        o Send continuous stream of messages at given interval till stop() is called
        
    Message have content msg_n, where n is a rising integer.  
    '''
    
    ECHO_TOPIC_NAME = 'echo'
    
    def __init__(self):
        
        threading.Thread.__init__(self)
        
        deliveryCallback = functools.partial(self.echoRequestDelivery)
        
        self.done    = False
        self.bus = BusAdapter()
        self.bus.subscribeToTopic(EchoServer.ECHO_TOPIC_NAME, deliveryCallback)
        
        self.echoRequestCondition = threading.Condition()
        self.start()
    
    def stop(self):
        self.done = True
        # Release thread from its wait():
        self.echoRequestCondition.acquire()
        self.echoRequestCondition.notifyAll()
        self.echoRequestCondition.release()
                    
    def echoRequestDelivery(self, topicName, rawResult, msgOffset):
        try:
            resDict = json.loads(rawResult)
            self.strToEcho = resDict['content']
            self.msgId     = resDict['id']
            # Only act on requests! Not on the 
            # responses we send with the echo:
            if resDict['type']  == 'resp':
                return
        except ValueError:
            # Not a JSON stucture, just echo as is:
            self.strToEcho = rawResult
            self.msgId     = '0'
            self.msgType   = 'req'

        self.echoRequestCondition.acquire()
        self.echoRequestCondition.notifyAll()
        self.echoRequestCondition.release()
        
    def run(self):
        
        while not self.done:
            
            self.echoRequestCondition.acquire()
            self.echoRequestCondition.wait()
            self.echoRequestCondition.release()

            # Did someone call stop()?
            if self.done:
                return

            self.bus.publish(self.strToEcho, EchoServer.ECHO_TOPIC_NAME, msgType='resp', msgId=self.msgId)
            print("Echoing '%s'" % self.strToEcho)

if __name__ == '__main__':
    EchoServer()
'''
Created on May 20, 2015

@author: paepcke
'''
import functools
import threading
import time
import unittest

from kafka_bus_python.kafka_bus import BusAdapter


TEST_ALL = True

class TestKafkaBus(unittest.TestCase):

    
    def setUp(self):
        self.bus = BusAdapter()
        self.deliveryFunc = functools.partial(self.deliverMessage)
        
    def tearDown(self):
        self.bus.close()

    @unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testSubscription(self):

        self.bus.subscribeToTopic('test')

        # Check that BusAdapter has properly remembered
        # the thread that resulted from above subscription:
        self.assertEqual(self.bus.listenerThreads['test'].listeners(), [self.bus.resultCallback])
        
        # One topic event:
        self.assertEqual(len(self.bus.topicEvents), 1)
        
        # Unsubscribing a topic that we didn't subscribe
        # to should be harmless:
        self.bus.unsubscribeFromTopic('badTopic')
        self.assertEqual(self.bus.listenerThreads['test'].listeners(), [self.bus.resultCallback])
        
        # Seriously unsubscribe:
        self.bus.unsubscribeFromTopic('test')
        self.assertEqual(len(self.bus.listenerThreads), 0)
        
    @unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testSubscribeToTopic(self):
        
        self.bus.subscribeToTopic('test', deliveryCallback=self.deliveryFunc)

        # Create a producer that immediately sends a single message
        # to topic 'test', and then goes away:
        TestProducer('test')
        
        # Hang for (at most) 1 second. Then a message
        # should be there:
        self.bus.waitForMessage('test', '1')
        
        self.assertEqual(self.topicName, 'test')
        self.assertTrue(self.rawResult.startswith('msg_'))
        self.assertTrue(type(self.msgOffset) == int)
        
    def deliverMessage(self, topicName, rawResult, msgOffset):
        self.topicName = topicName
        self.rawResult = rawResult
        self.msgOffset = msgOffset
        

class TestProducer(threading.Thread):
    
    def __init__(self, topicName, waitForTrigger=False, delayBetweenMessages=None):

        threading.Thread.__init__(self)
        
        self.topicName = topicName
        self.waitForTrigger = waitForTrigger
        self.delayBetweenMessages = delayBetweenMessages
        self.trigger = False
        self.counter = 0
        self.done    = False
        
        self.start()
    
    def stop(self):
        self.done = True
        
    def run(self):
        
        bus = BusAdapter()
        
        if self.waitForTrigger:
            while not self.trigger:
                time.sleep(0.5)
                
        bus.publish('msg_%d' % self.counter, 'test')
        if self.delayBetweenMessages is None:
            # Was a one-shot publish request:
            return

        while not self.done:
            time.sleep(self.delayBetweenMessages)
            if self.done:
                continue
            self.counter += 1
            bus.publish('msg_%d' % self.counter, 'test')

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
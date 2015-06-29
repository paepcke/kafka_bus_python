'''
Created on May 20, 2015

@author: paepcke
'''
import functools
import logging
import threading
import time
import unittest

from kafka_bus_python.kafka_bus import BusAdapter
from kafka_bus_python.test.echo_service import EchoServer


TEST_ALL = False

class TestKafkaBus(unittest.TestCase):

    
    def setUp(self):
        self.bus = BusAdapter()
        
        #Elog = logging.getLogger("kafka")
        #log.setLevel(logging.DEBUG)
        
        self.deliveryFunc     = functools.partial(self.deliverMessage)
        self.altDeliveryFunc  = functools.partial(self.altDeliverMessage)
        self.deliveryEvent    = threading.Event()
        self.altDeliveryEvent = threading.Event()
        
        self.testTopic = 'test1'
        
    def tearDown(self):
        self.bus.unsubscribeFromTopic(self.testTopic)
        try:
            # If a test producer was running, stop it:
            self.testProducer.stop()
            self.testProducer.join(3)
            if self.testProducer.is_alive():
                raise RuntimeError('Could not kill testProducer.')
        except:
            pass
        self.deliveryEvent.clear()
        self.altDeliveryEvent.clear()
        self.bus.close()

    #--------------------------------------------  Test Methods ------------------------

    @unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testSubscription(self):

        self.bus.subscribeToTopic(self.testTopic)

        # Check that BusAdapter has properly remembered
        # the thread that resulted from above subscription:
        self.assertEqual(self.bus.listenerThreads[self.testTopic].listeners(), [self.bus.resultCallback])
        
        # One topic event:
        self.assertEqual(len(self.bus.topicEvents), 1)
        
        # Unsubscribing a topic that we didn't subscribe
        # to should be harmless:
        self.bus.unsubscribeFromTopic('badTopic')
        self.assertEqual(self.bus.listenerThreads[self.testTopic].listeners(), [self.bus.resultCallback])
        
        # Seriously unsubscribe:
        self.bus.unsubscribeFromTopic(self.testTopic)
        self.assertEqual(len(self.bus.listenerThreads), 0)
        
    @unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testWaitForMessage(self):
        
        self.bus.subscribeToTopic(self.testTopic, deliveryCallback=self.deliveryFunc, kafkaLiveCheckTimeout=5)

        # Create a producer that immediately sends a single message
        # to topic self.testTopic, and then goes away:
        self.testProducer = TestProducer(self.testTopic)
        
        # Make sure msg is received:
        self.assertTrue(self.awaitExpectedMsg())
        self.assertMsgContentReasonable()        
        
    @unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testUnsubscribe(self):
        
        self.bus.subscribeToTopic(self.testTopic, deliveryCallback=self.deliveryFunc)
        
        # Ask test producer to fire a msg each time 
        # we call setTrigger():
        self.testProducer = TestProducer(self.testTopic, waitForTrigger=True, delayBetweenMessages=0)
        
        # Fire first msg:
        self.testProducer.setTrigger()
        # Make sure msg is received:
        self.assertTrue(self.awaitExpectedMsg())
        self.assertMsgContentReasonable()
        
        # Fire second msg:
        self.testProducer.setTrigger()
        # Make sure second msg is received:
        self.assertTrue(self.awaitExpectedMsg())
        self.assertMsgContentReasonable()
                
        # Unsubscribe:
        self.bus.unsubscribeFromTopic(self.testTopic)
        
        # Fire third msg:
        self.testProducer.setTrigger()
        
        # Make sure second msg is received:
        with self.assertRaises(NameError):
            self.awaitExpectedMsg(timeToWait=2.0)

    @unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testRemoveListener(self):
        
        self.bus.subscribeToTopic(self.testTopic, deliveryCallback=self.deliveryFunc)
        
        # Ask test producer to fire a msg each time 
        # we call setTrigger():
        self.testProducer = TestProducer(self.testTopic, waitForTrigger=True, delayBetweenMessages=0)
        
        # Fire first msg:
        self.testProducer.setTrigger()
        # Make sure msg is received:
        self.assertTrue(self.awaitExpectedMsg())
        self.assertMsgContentReasonable()
        
        self.bus.removeTopicListener(self.testTopic, self.deliveryFunc)
        
        # Make sure second msg is NOT received:
        self.topicName = None
        self.rawResult = None
        self.msgOffset = None

        # Fire second msg; will be handled
        # by BusAdapter's default handler, which does nothing:
        self.deliveryEvent.clear()
        self.testProducer.setTrigger()
        self.deliveryEvent.wait(5)
        # If our delivery msg had been called,
        # the self.deliveryEvent would now be set:
        self.assertFalse(self.deliveryEvent.isSet())
        
        # Just to make double sure:
        self.assertIsNone(self.topicName)
        self.assertIsNone(self.rawResult)
        self.assertIsNone(self.msgOffset)
        
        # Re-install the test listener:
        self.bus.addTopicListener(self.testTopic, deliveryCallback=self.deliveryFunc)
        
        # Ensure msg arrives:
        self.deliveryEvent.clear()

        # Fire another msg:
        self.testProducer.setTrigger()

        self.assertTrue(self.awaitExpectedMsg())
        
        # Ensure that our test delivery method was called:
        self.deliveryEvent.wait(5)
        self.assertTrue(self.deliveryEvent.isSet())
        
        # This time self.deliveryFunc should have been called
        # and should have set the msg elements:
        self.assertMsgContentReasonable()

    @unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testTwoListeners(self):
        
        self.bus.subscribeToTopic(self.testTopic, deliveryCallback=self.deliveryFunc)
        
        # Ask test producer to fire a msg each time 
        # we call setTrigger():
        self.testProducer = TestProducer(self.testTopic, waitForTrigger=True, delayBetweenMessages=0)
    
        # Install a second test listener:
        self.bus.addTopicListener(self.testTopic, deliveryCallback=self.altDeliveryFunc)
        
        # Reset both listener functions' events:
        self.deliveryEvent.clear()
        self.altDeliveryEvent.clear()

        # Fire an event:
        self.testProducer.setTrigger()
        
        # Ensure msg arrives:
        self.deliveryEvent.wait(5)
        self.altDeliveryEvent.wait(5)

        self.assertTrue(self.deliveryEvent.isSet())
        self.assertTrue(self.altDeliveryEvent.isSet())

    #@unittest.skipIf(not TEST_ALL, "Temporarily disabled")    
    def testSynchronousCall(self):

        subscriptionsOnEntry = self.bus.mySubscriptions()

        # Start an echo service:
        echoService = EchoServer()
        try:
            echoRes = self.bus.publish('This is a test', 'echo', sync=True)
            self.assertEqual(echoRes, 'This is a test')
        finally:
            echoService.stop()
            echoService.join(5)
            if echoService.isAlive():
                raise RuntimeError("Could not kill echo server.")
            
            # Now we should only have subscriptions that were
            # already there on entry to this method:
            self.assertEqual(subscriptionsOnEntry, self.bus.mySubscriptions())

    #--------------------------------------------  Support Methods ------------------------

        
    def awaitExpectedMsg(self, timeToWait=5.0):
        '''
        Wait for a message, and return True if the 
        msg arrived within less than 5sec. Else
        return False
    
        :param timeToWait: how many seconds maximally to wait till 
            concluding that msg won't arrive
        :type timeToWait: float
        :return: boolean indicating whether or not a msg was received within 5sec
        :rtype: boolean
        '''

        # Hang for (at most) 5 seconds. Then a message
        # should be there:
        timeBeforeWait = time.time()
        
        self.bus.waitForMessage(self.testTopic, 5)
        
        timeAfterWait  = time.time()
        
        # Elapsed time should be less than the 5sec timeout,
        # i.e. the wait should have released b/c a msg arrived:
        return (timeAfterWait - timeBeforeWait < 5)

    def assertMsgContentReasonable(self):
        '''
        
        Checks that a recently received message has
        topic self.testTopic, that the payload starts with msg,
        and that offset info is an int.
        
        '''

        # Make sure msg has reasonable content:        
        self.assertEqual(self.topicName, self.testTopic)
        resDict = eval(self.rawResult)
        self.assertTrue('content' in resDict.keys())
        self.assertTrue('time' in resDict.keys())
        self.assertTrue('type' in resDict.keys())
        self.assertTrue('id' in resDict.keys())
        self.assertTrue(type(self.msgOffset) == int)
        
        
    def deliverMessage(self, topicName, rawResult, msgOffset):
        self.topicName = topicName
        self.rawResult = rawResult
        self.msgOffset = msgOffset
        self.deliveryEvent.set()

    def altDeliverMessage(self, topicName, rawResult, msgOffset):
        self.altDeliveryEvent.set()

        

#--------------------------------------------  Test Producer for Kafka Msgs ------------------------

class TestProducer(threading.Thread):
    '''
    Producer thread. Can be called with the following
    characteristics:
    
        * Send a msg once
        * Before sending any (one or cyclically) more msgs only after method setTrigger() was called.
        * Send continuous stream of messages at given interval till stop() is called
        
    Message have content msg_n, where n is a rising integer.  
    '''
    
    def __init__(self, topicName, waitForTrigger=False, delayBetweenMessages=None):
        '''
        If delayBetweenMessages is a number in seconds, then a message
        will be sent every delayBetweenMessages. Else exactly one msg
        is sent. If waitForTrigger is True, then sleep between each 
        msg send until setTrigger() was called. I.e. each send is triggered
        by a new setTrigger() call from the outside.         
        
        :param topicName: name of topic to publish to
        :type topicName: string
        :param waitForTrigger: if True, outsider must call setTrigger() each 
            time a msg is to be sent. 
        :type waitForTrigger: boolean
        :param delayBetweenMessages: interval between sending msgs till stop() is called.
            None: only send a single method.
            0: keep sending messages as fast as possible. (Not recommended, unless waitForTrigger == True)
            n.m: seconds between sends
        :type delayBetweenMessages: {None | int | float}
        '''

        threading.Thread.__init__(self)
        
        self.topicName = topicName
        self.waitForTrigger = waitForTrigger
        self.delayBetweenMessages = delayBetweenMessages
        self.triggerEvent = threading.Event()
        self.msgNumber = 0
        self.done    = False
        
        self.start()
    
    def mostRecentMsgNum(self):
        return(self.msgNumber)
    
    def setTrigger(self):
        self.triggerEvent.set()
        
    def stop(self):
        self.done = True
        self.setTrigger()
        
    def run(self):
        
        bus = BusAdapter()
        
        while not self.done:

            if self.waitForTrigger:
                self.triggerEvent.wait()
                self.triggerEvent.clear()
            
            # Did someone call stop()?    
            if self.done:
                return
            
            self.msgNumber += 1
            bus.publish('msg_%d' % self.msgNumber, self.topicName)
            
            if self.delayBetweenMessages is not None:
                time.sleep(self.delayBetweenMessages)
                # Did someone call stop()    
                if self.done:
                    return
            else:
                return
            
if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
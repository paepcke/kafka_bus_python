'''
Created on May 19, 2015

@author: paepcke
'''

from functools import partial
import functools
import threading
import types

from kafka import SimpleProducer, KafkaClient
from kafka.common import KafkaTimeoutError

from kafka_bus_python.topic_waiter import TopicWaiter


class BusAdapter(object):
    '''
    classdocs
    '''
    DEFAULT_KAFKA_LISTEN_PORT = 9092

    def __init__(self, host='localhost', port=None, moduleName=None):
        '''
        
        :param host:
        :type host:
        :param port:
        :type port:
        :param moduleName:
        :type moduleName:
        '''
        self.host = host
        if port is None:
            port = BusAdapter.DEFAULT_KAFKA_LISTEN_PORT
        self.port = port
        self.moduleName = moduleName

        self.kafkaClient = KafkaClient("%s:%s" % (host,port))
        self.producer    = SimpleProducer(self.kafkaClient)

        # Create a function that has the first method-arg
        # 'self' already built in. That new function is then
        # called with just the remaining positional/keyword parms.
        # In this case: see method :func:`addTopicListener`.
        
        # This way we can by default pass :func:`deliverResult` to a
        # TopicWaiter instance, and thereby cause it to invoke our
        # deliverResult() *method* (which takes the hidden 'self.'
        # Yet other callers to subscribeToTopic() can specify 
        # a *function* which only takes the non-self parameters 
        # specified in method :func:`addTopicListener`. 
        
        self.resultCallback = partial(self.deliverResult)
        
        # Dict mapping topic names to thread objects that listen
        # to the respective topic. Used by subscribeToTopic() and
        # unsubscribeFromTopic():
        self.listenerThreads = {}
        
        # Dict mapping topic names to event objects that provide
        # communication between the topic's thread and the main
        # thread. Used in awaitMessage():
        self.topicEvents = {}
     
    def publish(self, busMessage, topicName=None, auth=None):
        '''
        Publish either a string or a BusMessage object. If busMessage
        is a string, then the caller is responsible for ensuring that
        the string is UTF-8, and a topic name must be provided.
        
        If busMessage is a BusMessage object, then that object contains
        all the required information. In this case, parameter topicName
        overrides a topic name that might be stored in the BusMessage.
        
        :param busMessage: string or BusMessage to publish
        :type busMessage: {string | BusMessage}
        :param topicName: name of topic to publish to. If None, then 
            parameter must be a BusMessage object that contains an
            associated topic name.
        :type topicName: {string | None}
        :param auth: reserved for later authentication mechanism.
        :type auth: not yet known
        '''

        if type(busMessage) == types.StringType:
            # We were passed a raw string to send. The topic name
            # to publish to better be given:
            if topicName is None:
                raise ValueError('Attempt to publish a string without specifying a topic name.')
            msg = busMessage
        else:
            # the busMessage parm is a BusMessage instance:
            # If topicName was given, it overrides any topic name
            # associated with the BusObject; else:
            if topicName is None:
                # Grab topic name from the BusMessage:
                topicName = busMessage.topicName()
                # If the BusMessage did not include a topic name: error
                if topicName is None:
                    raise ValueError('Attempt to publish a BusMessage instance that does not hold a topic name: %s' % str(busMessage))
            # Get the serialized, UTF-8 encoded message from the BusMessage:
            msg = busMessage.content()
        
        try:
            self.kafkaClient.ensure_topic_exists(topicName, timeout=5)
        except KafkaTimeoutError:
            raise("Topic %s is not a recognized topic." % topicName)
        
        self.producer.send_messages(topicName, msg)

    def subscribeToTopic(self, topicName, deliveryCallback=None):
        '''
        Fork a new thread that keeps waiting for any messages
        on the topic of the given name. Stop listening for the topic
        by calling unsubscribeFromTropic(). 
        
        For convenience, a deliveryCallback function may be passed,
        saving a subsequent call to addTopicListener(). See addTopicListener()
        for details.
        
        If deliveryCallback is absent or None, then method deliverResult()
        in this class will be used. That method is designed to be a 
        placeholder with no side effects.
        
        It is a no-op to call this method multiple times for the
        same topic.
                 
        :param topicName: official name of topic to listen for.
        :type topicName: string
        :param deliveryCallback: a function that takes two args: a topic
            name, and a topic content string.
        :type deliveryCallback: function
        '''
        
        if deliveryCallback is None:
            deliveryCallback = self.resultCallback
            
        if deliveryCallback != types.FunctionType and type(deliveryCallback) != functools.partial:
            raise ValueError("Parameter deliveryCallback must be a function, was of type %s" % type(deliveryCallback))

        try:
            # Does a thread for this msg already exist?
            self.listenerThreads[topicName]
            # Yep (b/c we didn't bomb out). Nothing to do:
            return
        
        except KeyError:
            # No thread exists for this topic. 
            
            # Create an event object that the thread will set()
            # whenever a msg arrives, even if no listeners exist:
            event = threading.Event()
            self.topicEvents[topicName] = event
            
            # Create the thread that will listen to Kafka:
            waitThread = TopicWaiter(topicName, self, deliveryCallback, event)
            # Remember that this thread listens to the given topic:
            self.listenerThreads[topicName] = waitThread
            
            waitThread.start()

    def unsubscribeFromTopic(self, topicName):
        '''
        Unsubscribes from topic. Stops the topic's thread,
        and removes it from bookkeeping so that the Thread object
        will be garbage collected. Same for the Event object
        used by the thread to signal message arrival.
        
        Calling this method for a topic that is already
        unsubscribed is a no-op.
        
        :param topicName: name of topic to subscribe from
        :type topicName: string
        '''

        # Delete our record of the Event object used by the thread to
        # indicate message arrivals:
        try:
            del self.topicEvents[topicName]
        except KeyError:
            pass

        try:
            # Does a thread for this msg even exist?
            existingWaitThread = self.listenerThreads[topicName]

            # Yep, it exists. Stop it and remove it from
            # our bookkeeping
            existingWaitThread.stop()
            del self.listenerThreads[topicName]
            
        except KeyError:
            # No thread exists for this topic at all, so all done:
            return
    
    def addTopicListener(self, topicName, deliveryCallback):
        '''
        Add a listener function for a topic for which a
        subscription already exists. Parameter deliverCallback
        must be a function accepting parameters:
            topicName, rawResult, msgOffset
        It is an error to call the method without first
        having subscribed to the topic.
        
        :param topicName:
        :type topicName:
        :param deliveryCallback:
        :type deliveryCallback:
        :raise NameError if caller has not previously subscribed to topicName.
        '''
        
        if deliveryCallback != types.FunctionType and type(deliveryCallback) != functools.partial:
            raise ValueError("Parameter deliveryCallback must be a function, was of type %s" % type(deliveryCallback))
        try:
            # Does a thread for this msg already exist?
            existingWaitThread = self.listenerThreads[topicName]
            
            # Yep (b/c we didn't bomb out). Check whether the 
            # given deliveryCallback is already among the listeners 
            # added earlier:
            if existingWaitThread.listeners().index(deliveryCallback) > -1:
                # If both, a thread and this callback exist, do nothing:
                return
            # Thread exists for this topic, but an additional
            # callback is being registered:
            existingWaitThread.addListener(deliveryCallback)
            return
        except KeyError:
            # No thread exists for this topic, so no deliveryCallback
            # can be added:
            raise NameError("Attempt to add topic listener %s for topic '%s' without first subscribing to '%s'" %
                            (str(deliveryCallback), topicName, topicName))
        
    
    def removeTopicListener(self, topicName, deliveryCallback):
        '''
        Remove a topic listener function from a topic. It is
        a no-op to call this method with a topic that has not
        been subscribed to, or with a deliveryCallback function that
        was never added to the topic.
        
        :param topicName:
        :type topicName:
        :param deliveryCallback:
        :type deliveryCallback:
        '''
        
        try:
            # Does a thread for this msg even exist?
            existingWaitThread = self.listenerThreads[topicName]

            # Yep, exists (we didn't bomb). Now check whether the 
            # given deliveryCallback was actually added to the listeners 
            # earlier:

            existingListeners = existingWaitThread.listeners()
            if existingListeners.index(deliveryCallback) == -1:
                # This listener isn't registered, so all done:
                return
            
            existingWaitThread.removeListener(deliveryCallback)
            return 
        except KeyError:
            # No listener thread exists for this topic at all, so all done:
            return


    def deliverResult(self, topicName, rawResult, msgOffset):
        '''
        Simple default message delivery callback. Just prints 
        topic name and content. Override in subclass to get 
        more interesting behavior. Remember, though: you (I believe)
        need to do the functools.partial trick to create a function
        for your overriding method that already has 'self' curried out.
        We may be able to simplify that, because the listening threads
        do save the BusAdapter objecst that created them.    
        
        :param topicName: name of topic the msg came from
        :type topicName: string
        :param rawResult: the string from the wire; not yet de-serialized
        :type rawResult: string
        :param msgOffset: the Kafka queue offset of the message
        :type msgOffset: int 
        '''
        print('Msg at offset %d: %s' % (msgOffset,rawResult))
        
        
    def waitForMessage(self, topicName, timeout=None):
        '''
        Block till a message on the given topic arrives. It is
        an error to call this method on a topic to which the
        caller has not previously subscribed.
        
        :param topicName:
        :type topicName:
        :param timeout:
        :type timeout:
        :raise NameError on attempt to wait for a topic for which no subscription exists.
        '''
        
        try:
            event = self.topicEvents[topicName]
            event.wait()
        except KeyError:
            raise NameError("Attempt to wait for messages on topic %s, which was never subscribed to." % topicName)
        
    def close(self):
        '''
        Cleanup. All threads are stopped. Kafka
        connection is closed.
        '''
        for thread in self.listenerThreads.values():
            thread.stop()
        self.listenerThreads.clear()
        self.topicEvents.clear()
        
        self.kafkaClient.close()

    
    
# from kafka import SimpleProducer, KafkaClient
# from random import randint
# 
# # Producer module sends out Kafka messages on port 9092
# k = KafkaClient("localhost:9092")
# producer = SimpleProducer(k)
# 
# # User specifies name for event log (e.g. name of module or activity)
# title = str(raw_input("Name event log: "))
# k.ensure_topic_exists(title)
# 
# # Unique user sends messages as needed.
# uid = "Learner" + str(randint(0, 20000))
# while True:
#     event = raw_input("Add what to event log?: ('Q' to end.): ")
#     if event == 'Q':
#         break
#     else:
#         msg = event.encode('UTF-8', 'ignore')
#         producer.send_messages(title, "%s: %s" % (uid, msg))
# 
# # Module closes connection on exit.
# k.close()
    
'''
Created on May 19, 2015

@author: paepcke
'''

from functools import partial

from kafka import SimpleProducer, KafkaClient
from kafka.common import KafkaTimeoutError
from kafka_bus_python.topic_waiter import TopicWaiter


class BusModule(object):
    '''
    classdocs
    '''
    DEFAULT_PORT = 9092

    def __init__(self, host='localhost', port=BusModule.DEFAULT_PORT, moduleName=None):
        '''
        
        :param host:
        :type host:
        :param port:
        :type port:
        :param moduleName:
        :type moduleName:
        '''
        self.host = host
        self.port = port
        self.moduleName = moduleName

        self.kafkaClient = KafkaClient("%:%" % (host,port))
        self.producer    = SimpleProducer(self.kafkaClient)

        # Create a function that has the first method-arg
        # 'self' already built in. It is call with just the
        # single arg 'rawResult':
        self.resultCallback = partial(self.deliverResult, self)
        
        self.listenerThreads = {}
     
    def publish(self, busTopicObj, callback=None, auth=None):
        if callback is None:
            callback = self.resultCallback
            
        topicName = busTopicObj.name
        try:
            self.kafkaClient.ensure_topic_exists(topicName, timeout=5)
        except KafkaTimeoutError:
            raise("Topic %s is not a recognized topic." % topicName)
        
        msg = busTopicObj.content.encode('UTF-8', 'ignore')
        self.producer.send_messages(topicName, msg)

    def listenForTopic(self, topicName, deliveryCallback=None):
        '''
        Fork a new thread that keeps waiting for any messages
        on the topic of the given name. Stop listening for the topic
        by calling dropTropic(). It is OK to call this method multiple
        times with the same topic name. Only one thread will be forked,
        but different delivery callback functions may be specified each
        time. All the functions will be called for each incoming msg
        on the topic.
                 
        :param topicName: official name of topic to listen for.
        :type topicName: string
        :param deliveryCallback: a function that takes two args: a topic
            name, and a topic content string.
        :type deliveryCallback: function
        '''
        
        try:
            # Does a thread for this msg already exist?
            existingWaitThread = self.listenerThreads[topicName]
            # Yep. Check whether the given deliveryCallback is
            # already among the listeners added earlier:
            if existingWaitThread.listeners().index(deliveryCallback) > -1:
                return
            existingWaitThread.addListener(deliveryCallback)
            return 
        except KeyError:
            # No thread exists yet for this topic:
            existingWaitThread = TopicWaiter(topicName, self, deliveryCallback)
            self.listenerThreads[topicName] = existingWaitThread

    def dropTopic(self, topicName, deliveryCallback=None):

        try:
            # Does a thread for this msg even exist?
            existingWaitThread = self.listenerThreads[topicName]

            # Yep. Now check whether the given deliveryCallback was
            # actually added to the listeners earlier:

            existingListeners = existingWaitThread.listeners()
            if existingListeners.index(deliveryCallback) == -1:
                # This listener isn't registered, so all done:
                return
            
            existingWaitThread.removeListener(deliveryCallback)
            return 
        except KeyError:
            # No listener exists for this topic at all, so all done:
            return
    
    def deliverResult(self, topicName, rawResult):
        '''
        Simple default message delivery callback. Just prints 
        topic name and content. Override in subclass to get 
        more interesting behavior. Remember, though: you (I believe)
        need to do the functools.partial trick to create a function
        for your overriding method that already has 'self' curried out.
        We may be able to simplify that, because the listening threads
        do save the BusModule objecst that created them.    
        
        :param topicName:
        :type topicName:
        :param rawResult:
        :type rawResult:
        '''
        print('Result: %s' % rawResult)
        
    def close(self):
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
    
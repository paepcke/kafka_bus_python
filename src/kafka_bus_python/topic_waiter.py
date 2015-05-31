'''
Created on May 19, 2015

@author: paepcke
'''
import threading

from kafka.consumer import SimpleConsumer
from kafka.consumer.kafka import KafkaConsumer


class TopicWaiter(threading.Thread):
    '''
    classdocs
    '''

    # Max size of an incoming msg: 1MB
    fetch_message_max_bytes = 1024 * 1024 *1024

    def __init__(self, topicName, busAdapter, kafkaGroupId, deliveryCallback=None, eventObj=None):
        '''
        Initialize list of callback functions. Remember the Event object
        to raise whenever a message arrives.
        
        Assumption: the passed-in parent BusAdapter object contains
        instance variable bootstrapServers, which is initialized to
        an array of strings of the form hostName:port, in which each
        hostName is a Kafka server, and each port is a port on which
        the Kafka server listens. Example: ['myKafkaServer.myplace.org:9092']. 
        
        :param topicName: Kafka topic to listen to
        :type topicName: string
        :param busAdapter: BusAdapter object that created this thread.
        :type busAdapter: BusAdapter
        :param kafkaGroupId: name under which message offset management is
            stored [by Kafka in zookeeper]. Different groups of bus modules
            will have different sets of message offsets recorded.
        :type kafkaGroupId: string
        :param deliveryCallback: a function to call when a message on this topic arrives.
            See :func:`addTopicListener` in :class:`BusAdapter`.
        :type deliveryCallback: Function
        :param eventObj: optional :class:`threading.Event` object to set()
            when a message arrives.
        :type eventObj: threading.Event
        '''

        threading.Thread.__init__(self)
        self.topicName = topicName
        self.busModule = busAdapter
        self.kafkaGroupId = kafkaGroupId
        
        # We maintain an array of functions to call
        # when an event arrives:
        if deliveryCallback is None:
            self.deliveryCallbacks = [] 
        else:
            self.deliveryCallbacks = [deliveryCallback]
            
        # The optional threading.Event obj we'll set
        # when a message arrives:
        self.eventToSet = eventObj
        
        # Make sure the topic exists in the Kafka server.
        # If it did not exist before, the following call
        # will create it:
        self.busModule.kafkaClient.ensure_topic_exists(self.topicName)
        
#         self.kafkaConsumer = SimpleConsumer(self.busModule.kafkaClient, 
#                                             group=self.kafkaGroupId, 
#                                             topic=self.topicName, 
#                                             iter_timeout=None,    # wait forever
#                                             ) #****auto_commit=False)  
         
        self.kafkaConsumer = KafkaConsumer(self.topicName,
                                           group_id=self.kafkaGroupId,
                                           auto_commit_enable=True,
                                           auto_offset_reset='smallest',
                                           bootstrap_servers=self.busModule.bootstrapServers)
        
        # Use the recommended way of stopping a thread:
        # Set a variable that the thread checks periodically:
        self.done = False
        
    def addListener(self, callback):
        '''
        Add a listener who will be notified with any
        message that arrives on the topic. See :func:`addTopicListener` 
        in :class:`BusAdapter` for details on parameters.
        
        :param callback: function with two args: a topic name, and
            a string that is the message content.
        :type callback: function 
        '''
        self.deliveryCallbacks.append(callback)

    def removeListener(self, callback):
        '''
        Remove the specified function from the callbacks to
        notify upon message arrivals. It is a no-op to
        remove a non-existing listener.
        
        :param callback: callback function to remove. 
        :type callback: Function
        '''

        try:
            self.deliveryCallbacks.remove(callback)
        except ValueError:
            # This callback func wasn't registered
            # in the first place:
            return

    def listeners(self):
        '''
        Return all the callback functions that will be called
        each time a message arrives.
        
        :returns list of registered callback functions.
        '''
        
        return self.deliveryCallbacks

    def run(self):
        '''
        Hang on Kafka message arrival. Whenever a message arrives,
        set() the :class:`threading.Event` object, if one was provided
        to the __init__() method. Then all all the registered delivery
        functions in turn.
        
        Periodically check whether self.done is True, indicating that
        thread should stop.
        '''
        
        while not self.done:
            
            # Hang for a msg to arrive:
            
            # *****Can currently throw:
            #   FailedPayloadsError: [FetchRequest(topic='test', partition=0, offset=41, max_bytes=4096)]
            #   No handlers could be found for logger "kafka"
            # Need to figure out why.

            # We get an iterator feeding out KafkaMessage
            # objects:  KafkaMessage(topic='learner_homework_history', 
            #                        partition=0, 
            #                        offset=0, 
            #                        key=None, 
            #                        value='My message body')

            # the SimpleConsumer() call:
            for kafkaMessage in self.kafkaConsumer:
                msgContent = kafkaMessage.value.decode('UTF-8')
                msgOffset  = kafkaMessage.offset
                
                # Deliver the message to all registered callbacks:
                for deliveryFunc in self.deliveryCallbacks:
                    deliveryFunc(self.topicName, msgContent, msgOffset)
                    
                    # Delivered msg to all the delivery funcs.
                    # Tell Kafka that we are done with this msg:
                    self.kafkaConsumer.task_done(kafkaMessage)
                    self.kafkaConsumer.commit()
                    
                    # Was the stop() method called?
                    if self.done:
                        break
                if self.eventToSet is not None:
                    self.eventToSet.set()
                    
                # Was the stop() method called?
                if self.done:
                    break
        
    def stop(self):
        self.done = True
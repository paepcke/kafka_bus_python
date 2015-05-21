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

    def __init__(self, topicName, busAdapter, deliveryCallback=None, eventObj=None):
        '''
        Initialize list of callback functions. Remember the Event object
        to raise whenever a message arrives.
        
        :param topicName: Kafka topic to listen to
        :type topicName: string
        :param busAdapter: BusAdapter object that created this thread.
        :type busAdapter: BusAdapter
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
        
        # We maintain an array of functions to call
        # when an event arrives:
        if deliveryCallback is None:
            self.deliveryCallbacks = [] 
        else:
            self.deliveryCallbacks = [deliveryCallback]
            
        # The optional threading.Event obj we'll set
        # when a message arrives:
        self.eventToSet = eventObj
        
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
        
        # Consumer prints out all events logged by any producer. Times out in 3 minutes.
        while not self.done:
            
            # Hang for a msg to arrive:
            topicMsgs = SimpleConsumer(self.busModule.kafkaClient, 
                                       group=None, 
                                       topic=self.topicName, 
                                       iter_timeout=180, 
                                       auto_commit=False)
            # *****Can currently throw:
            #   FailedPayloadsError: [FetchRequest(topic='test', partition=0, offset=41, max_bytes=4096)]
            #   No handlers could be found for logger "kafka"
            # Need to figure out why.

            # We get an array of OffsetAndMessage objects from
            # the SimpleConsumer() call:
            for offsetAndMessageObj in topicMsgs:
                msgContent = offsetAndMessageObj.message.value.decode('UTF-8')
                msgOffset  = offsetAndMessageObj.offset
                
                # Deliver the message to all registered callbacks:
                for deliveryFunc in self.deliveryCallbacks:
                    deliveryFunc(self.topicName, msgContent, msgOffset)
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
'''
Created on May 19, 2015

@author: paepcke
'''

from datetime import datetime
from functools import partial
import functools
import json
import logging
import threading
import types
import uuid

from kafka.client import KafkaClient
from kafka.common import KafkaTimeoutError, KafkaUnavailableError
from kafka.producer.simple import SimpleProducer

from kafka_bus_python.kafka_bus_utils import JSONEncoderBusExtended
from kafka_bus_python.topic_waiter import TopicWaiter


class BusAdapter(object):
    '''
    The BusAdapter class is intended to be imported to bus modules.
    
    'id'     : <RFC 4122 UUID Version 4>   # e.g. 'b0f4259e-3d01-44bd-9eb3-25981c2dc643'
    'type'   : {req | resp}
    'status' : { OK | ERROR }
    'time'   : <ISO 8601>                  # e.g. '2015-05-31T17:13:41.957350'
    'content': <text>
    
    '''
    DEFAULT_KAFKA_LISTEN_PORT = 9092
    KAFKA_SERVERS = [('localhost', DEFAULT_KAFKA_LISTEN_PORT),
                     ('mono.stanford.edu', DEFAULT_KAFKA_LISTEN_PORT),
                     ('datastage.stanford.edu', DEFAULT_KAFKA_LISTEN_PORT),
                     ]
       
    # Remember whether logging has been initialized (class var!):
    loggingInitialized = False
    logger = None

    def __init__(self, 
                 kafkaHost=None, 
                 kafkaPort=None,
                 loggingLevel=logging.DEBUG,
                 logFile=None,
                 kafkaGroupId='school_bus'
                 ):
        '''
        Initialize communications with Kafka.

        :param kafkaHost: hostname or ip address of host where Kafka server runs.
            If None, then BusAdapter.KAFKA_SERVERS are tried in turn.
        :type kafkaHost: {string | None}
        :param kafkaPort: port at which Kafka expects clients to come in.
            if None, then BusAdapter.DEFAULT_KAFKA_LISTEN_PORT is used.
        :type kafkaPort: {int | None}
        :param loggingLevel: detail of logging
        :type loggingLevel: {logging.DEBUG | logging.INFO | logging.ERROR}  
        :param logFile: file to which log is written; concole, if NONE
        :type logFile: {string | None}
        :param kafkaGroupId: name under which message offset management is
            stored [by Kafka in zookeeper]. Different groups of bus modules
            will have different sets of message offsets recorded. You can 
            leave this default.
        :type kafkaGroupId: string
        '''

        if kafkaPort is None:
            kafkaPort = BusAdapter.DEFAULT_KAFKA_LISTEN_PORT
        self.port = kafkaPort
        self.kafkaGroupId = kafkaGroupId
        
        self.setupLogging(loggingLevel, logFile)

        try:
            for hostPortTuple in BusAdapter.KAFKA_SERVERS:
                self.logDebug('Contacting Kafka server at %s:%s...' % hostPortTuple)
                self.kafkaClient = KafkaClient("%s:%s" % hostPortTuple)
                self.logDebug('Successfully contacted Kafka server at %s:%s...' % hostPortTuple)
                # If succeeded, init the 'bootstrap_servers' array
                # referenced in topic_waiter.py:
                self.bootstrapServers = ['%s:%s' % hostPortTuple]
                # Don't try any other servers:
                break
        except KafkaUnavailableError:
            raise KafkaUnavailableError("No Kafka server found running at any of %s." % str(BusAdapter.KAFKA_SERVERS))
                
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
        
        # Dict used for synchronous calls: the dict maps
        # msg UUIDs to the results of a call. Set in 
        # deliverResultUuidFilter(), and emptied in publish()
        self.resDict = {}

# --------------------------  Pulic Methods ---------------------
     
    def publish(self, busMessage, topicName=None, sync=False, timeout=None, auth=None):
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
        :param sync: if True, call will not return till answer received,
            or timeout (if given) has expired).
        :type sync: boolean
        :param timeout: timeout after which synchronous call should time out.
            if sync is False, the timeout parameter is ignored.
        :type timeout: float
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
            
        # Now msg contains the msg text.
        try:
            self.kafkaClient.ensure_topic_exists(topicName, timeout=5)
        except KafkaTimeoutError:
            raise("Topic %s is not a recognized topic." % topicName)
        
        # Create a JSON struct:
        msgUUID = str(uuid.uuid4())
        msgDict = dict(zip(['id', 'type', 'time', 'content'],
                           [msgUUID, 'req', datetime.now().isoformat(), msg]))

        self.producer.send_messages(topicName, json.dump(msgDict))
        
        # If synchronous operation requested, wait for response:
        if sync:
            self.uuidToWaitFor = msgUUID
            #*****: - save delivery func for this topic, if it's being
            #         subscribed to
            #       - Make delivery func for this topic subscription be self.deliverRsultUuidFilter (partial func)
            #       - wait for topic
            #       - unsubscribe, or reset subscription to original delivery func
            #       - get self.resDict[msgUUID], and del that entry in self.resDict
            #       - return the result Dict. 

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
            waitThread = TopicWaiter(topicName, self, self.kafkaGroupId, deliveryCallback=deliveryCallback, eventObj=event)
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
            try:
                existingWaitThread.listeners().index(deliveryCallback)
                # Both, a thread and this callback already exist, do nothing:
                return
            except ValueError:
                pass
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
            try:
                existingListeners.index(deliveryCallback)
                # The listener to be removed does exist:
                existingWaitThread.removeListener(deliveryCallback)
                return 
            except NameError:
                # This listener isn't registered, so all done:
                return
            
        except KeyError:
            # No listener thread exists for this topic at all, so all done:
            return


    def waitForMessage(self, topicName, timeout=None):
        '''
        Block till a message on the given topic arrives. It is
        an error to call this method on a topic to which the
        caller has not previously subscribed.
        
        :param topicName:
        :type topicName:
        :param timeout: seconds (or fractions of second) to wait.
        :type timeout: float
        :returns True if a message arrived in time, else returnes False
        :rtype boolean
        :raise NameError on attempt to wait for a topic for which no subscription exists.
        '''
        
        try:
            event = self.topicEvents[topicName]
            return(event.wait(timeout))
        except KeyError:
            raise NameError("Attempt to wait for messages on topic %s, which was never subscribed to." % topicName)
        
    def returnError(self, req_key, topicName, errMsg):
        errMsg = {'resp_key'    : req_key,
                  'status'      : 'ERROR',
                  'content'     : errMsg
                 }
        errMsgJSON = JSONEncoderBusExtended.makeJSON(errMsg)
        self.bus.publish(errMsgJSON, topicName)
      
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

# --------------------------  Private Methods ---------------------


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
        

    def deliverResultUuidFilter(self, topicName, rawResult, msgOffset):
        if self.uuidToWaitFor is not None:
            try:
                thisResDict = json.loads(rawResult)
            except ValueError e:
                # Bad JSON found; log and ignore:
                self.logWarn('Bad JSON while waiting for sync response: %s' rawResult)
                return
            # Is this a response msg, and is it the one
            # we are waiting for?
            thisUuid    = thisResDict.get('id', None)
            thisMsgType = thisResDict.get('type', None)
            if thisUuid    == self.uuidToWaitFor and \
               thisMsgType == 'resp':
                self.resDict['uuidToWaitFor'] = thisResDict
    
    def setupLogging(self, loggingLevel, logFile):
        if BusAdapter.loggingInitialized:
            # Remove previous file or console handlers,
            # else we get logging output doubled:
            BusAdapter.logger.handlers = []
            
        # Set up logging:
        # A logger named SchoolBusLog:
        BusAdapter.logger = logging.getLogger('SchoolBusLog')
        BusAdapter.logger.setLevel(loggingLevel)
        
        # A msg formatter that shows datetime, logger name, 
        # the log level of the message, and the msg.
        # The datefmt=None causes ISO8601 to be used:
        
        formatter = logging.Formatter(fmt='%(asctime)s-%(name)s-%(levelname)s: %(message)s',datefmt=None)
        
        # Create file handler if requested:
        if logFile is not None:
            handler = logging.FileHandler(logFile)
        else:
            # Create console handler:
            handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.setLevel(loggingLevel)
#         # create formatter and add it to the handlers
#         formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#         fh.setFormatter(formatter)
#         ch.setFormatter(formatter)
        # Add the handler to the logger
        BusAdapter.logger.addHandler(handler)
        #**********************
        #BusAdapter.logger.info("Info for you")
        #BusAdapter.logger.warn("Warning for you")
        #BusAdapter.logger.debug("Debug for you")
        #**********************
        
        BusAdapter.loggingInitialized = True


    def logWarn(self, msg):
        BusAdapter.logger.warn(msg)

    def logInfo(self, msg):
        BusAdapter.logger.info(msg)
     
    def logError(self, msg):
        BusAdapter.logger.error(msg)

    def logDebug(self, msg):
        BusAdapter.logger.debug(msg)


'''
Created on May 19, 2015

@author: paepcke
'''

'''
TODO: 
   o Logger should include module name
   o Do error responses in synchronous calls make it to LTI browser?
   o Write channel to browser
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

from kafka_bus_exceptions import SyncCallTimedOut, SyncCallRuntimeError, \
    BadInformation
from kafka_bus_python.bus_message import BusMessage
from kafka_bus_python.kafka_bus_utils import JSONEncoderBusExtended
from kafka_bus_python.topic_waiter import TopicWaiter


class BusAdapter(object):
    '''
    The BusAdapter class is intended to be imported to bus modules.
    Instances of this class provide the software bus illusion over
    Kafka. The most important methods are:
        
        * publish()
        * waitForMessage()
        * subscribeToTopic()
        * unSubscribeFromTopic()
    
    In addition, clients of this class may install multiple listeners
    for any given topic. The publish() method may be used asynchronously,
    just to send a message to subscribing modules on the bus, or
    synchronously like a remote procedure call.
        
    The BusAdapter wraps payloads into a JSON structure
    as follows: 
    
    'id'     : <RFC 4122 UUID Version 4>   # e.g. 'b0f4259e-3d01-44bd-9eb3-25981c2dc643'
    'type'   : {req | resp}
    'status' : { OK | ERROR }
    'time'   : <ISO 8601>                  # e.g. '2015-05-31T17:13:41.957350'
    'content': <text>
    
    It is the responsibility of listener functions to 
    strip this header away, if desired. For an example
    see echo_service.EchoServer's echoRequestDelivery()
    method.
    
    '''
    
    LEGAL_MSG_TYPES = ['req', 'resp']
    LEGAL_STATUS    = ['OK', 'ERROR']
    
    DEFAULT_KAFKA_LISTEN_PORT = 9092
    KAFKA_SERVERS = [('localhost', DEFAULT_KAFKA_LISTEN_PORT),
                     ('mono.stanford.edu', DEFAULT_KAFKA_LISTEN_PORT),
                     ('datastage.stanford.edu', DEFAULT_KAFKA_LISTEN_PORT),
                     ]

#     KAFKA_SERVERS = [('mono.stanford.edu', DEFAULT_KAFKA_LISTEN_PORT),
#                      ('localhost', DEFAULT_KAFKA_LISTEN_PORT),
#                      ('datastage.stanford.edu', DEFAULT_KAFKA_LISTEN_PORT),
#                      ]

       
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

        for hostPortTuple in BusAdapter.KAFKA_SERVERS:
            self.logDebug('Contacting Kafka server at %s:%s...' % hostPortTuple)
            try:
                self.kafkaClient = KafkaClient("%s:%s" % hostPortTuple)
            except KafkaUnavailableError:
                # Have we just contacted the last of the available
                # servers?
                if hostPortTuple == BusAdapter.KAFKA_SERVERS[-1]:
                    raise KafkaUnavailableError("No Kafka server found running at any of %s." % str(BusAdapter.KAFKA_SERVERS))
                else:
                    continue
            self.logDebug('Successfully contacted Kafka server at %s:%s...' % hostPortTuple)
            # If succeeded, init the 'bootstrap_servers' array
            # referenced in topic_waiter.py:
            self.bootstrapServers = ['%s:%s' % hostPortTuple]
            # Don't try any other servers:
            break
                
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
        
        self.resultCallback    = partial(self.deliverResult)
        
        # A function that will be called when the result to
        # a synchronous call arrives:
        self.syncResultWaiter  = partial(self.awaitSynchronousReturn)
        
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
        # awaitSynchronousReturn(), and emptied in publish()
        self.resDict = {}

# --------------------------  Pulic Methods ---------------------
     
    def publish(self, busMessage, topicName=None, sync=False, msgId=None, msgType='req', timeout=None, auth=None):
        '''
        Publish either a string or a BusMessage object. If busMessage
        is a string, then the caller is responsible for ensuring that
        the string is UTF-8, and a topic name must be provided.
        
        If busMessage is a BusMessage object, then that object contains
        all the required information. In this case, parameter topicName
        overrides a topic name that might be stored in the BusMessage.
        
        Messages are wrapped in a JSON structure that provides
        'id', 'type', 'time', and 'content' fields. The 'content' field
        will contain the message payload.
        
        Two ways of using this method: asynchronously, and synchronously.
        In asynchronous invocation the passed-in message is published, and
        this method returns immediately. For this type of invocation just
        provide argument busMessage, and possibly topicName, if busMessage
        is a string. 
        
        Synchronous invocation is just like a remote procedure call.
        In synchronous invocation the passed-in message is published, and 
        this method will wait for a return message that carries the same
        message ID, and is of message type 'resp'. This method then
        returns the **content** of the returned message; the surrounding
        wrapper (time/msgId/msgType...) is stripped.  
        
        :param busMessage: string or BusMessage to publish
        :type busMessage: {string | BusMessage}
        :param topicName: name of topic to publish to. If None, then 
            parameter must be a BusMessage object that contains an
            associated topic name.
        :type topicName: {string | None}
        :param sync: if True, call will not return till answer received,
            or timeout (if given) has expired).
        :type sync: boolean
        :param msgId: if this publish() call is a response to a prior request,
            the request message's ID must be the id of the response. In that
            case the caller can use this parameter to provide the ID. If
            None, a new message ID is generated.
        :type msgId: string
        :param msgType: value for the message type field of the outgoing message.
            Usually this is 'req', but when calling publish() to return a result
            to a prior request, then set this argument to 'resp'. 
        :param timeout: timeout after which synchronous call should time out.
            if sync is False, the timeout parameter is ignored.
        :type timeout: float
        :param auth: reserved for later authentication mechanism.
        :type auth: not yet known
        :return return value is only defined for synchronous invocation.
        :rtype string
        :raise ValueError if targeted topic name is not provided in a msg object,
            or explicitly in the topicName parameter.
        :raise ValueError if illegal message type is passed in.
        :raise BadInformation if Kafka does not recognize the provided topic
            **and** Kafka is not configured to create topics on the fly.
        :raise SyncCallTimedOut if no response is received to a synchronous call
            within the provided timeout period.
        :raise SyncCallRuntimeError if a message received in response to a 
            synchronous call cannot be parsed.
        '''

        if not isinstance(busMessage, BusMessage):
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
            raise BadInformation("Topic '%s' is not a recognized topic." % topicName)
        
        # Create a JSON struct:
        if msgId is None:
            msgUuid = str(uuid.uuid4())
        else:
            msgUuid = msgId
        # Sanity check on message type:
        if msgType not in BusAdapter.LEGAL_MSG_TYPES:
            raise ValueError('Legal message types are %s' % str(BusAdapter.LEGAL_MSG_TYPES))
        
        msgDict = dict(zip(['id', 'type', 'time', 'content'],
                           [msgUuid, msgType, datetime.now().isoformat(), msg]))

        # If synchronous operation requested, wait for response:
        if sync:
            
            # Before publishing the request, must prepare for 
            # a function that will be invoked with the result.
            
            # Use instance vars for communication with the result 
            # delivery thread.
            # Use of these instance vars means that publish
            # isn't re-entrant. Fine for now:

            # For the result delivery method to know which msg id
            # we are waiting for:            
            self.uuidToWaitFor   = msgUuid
            
            # For the result delivery method to know which topic
            # we are waiting for:
            self.topicToWaitFor  = topicName

            # For the result delivery method to put a string
            # if an error occurs while processing the result
            # bus message:

            self.syncResultError = None
            
            # Create event that will wake us when result
            # arrived and has been placed in self.resDict:

            self.resultArrivedEvent = threading.Event(timeout)

            # If not subscribed to the topic to which this synchronous
            # call is being published, then subscribe to it temporarily:

            wasSubscribed = topicName in self.mySubscriptions()
            if not wasSubscribed:
                self.subscribeToTopic(topicName, self.syncResultWaiter)
            else:
                self.addTopicListener(topicName, self.syncResultWaiter)
            
            # Finally: post the request...
            self.producer.send_messages(topicName, json.dumps(msgDict))
            
            # ... and wait for the answer message to invoke
            # self.awaitSynchronousReturn():
            resBeforeTimeout = self.resultArrivedEvent.wait(timeout)
            
            # Result arrived, and was placed into
            # self.resDict under the msgUuid. Remove the listener
            # that waited for the result:
            
            self.removeTopicListener(topicName, self.syncResultWaiter)
            
            # If we weren't subscribed to this topic, then
            # restore that condition:

            if not wasSubscribed:
                self.unsubscribeFromTopic(topicName)
            
            # If the 'call' timed out, raise exception:
            if not resBeforeTimeout:
                raise SyncCallTimedOut('Synchronous call on topic %s timed out' % topicName)
            
            # A result arrived from the call:
            res = self.resDict.get(msgUuid, None)
            
            # No longer need the result to be saved:
            try:
                del self.resDict[msgUuid]
            except KeyError:
                pass
            
            # Check whether awaitSynchronousReturn() placed an
            # error message into self.syncResultError:

            if self.syncResultError is not None:
                raise(SyncCallRuntimeError(self.syncResultError)) 
            
            return res
        
        else:
            # Not a synchronous call; just publish the request:
            self.producer.send_messages(topicName, json.dumps(msgDict))
       


    def subscribeToTopic(self, topicName, deliveryCallback=None, kafkaLiveCheckTimeout=30):
        '''
        Fork a new thread that keeps waiting for any messages
        on the topic of the given name. Stop listening for the topic
        by calling unsubscribeFromTropic(). 
        
        For convenience, a deliveryCallback function may be passed,
        saving a subsequent call to addTopicListener(). See addTopicListener()
        for details.
        
        If deliveryCallback is absent or None, then method deliverResult()
        in this class will be used. That method is intended to be a 
        placeholder with no side effects.
        
        It is a no-op to call this method multiple times for the
        same topic.
                 
        :param topicName: official name of topic to listen for.
        :type topicName: string
        :param deliveryCallback: a function that takes two args: a topic
            name, and a topic content string.
        :type deliveryCallback: function
        :param kafkaLiveCheckTimeout: timeout in (fractional) seconds to
            wait when checking for a live Kafka server being available.
        :type kafkaLiveCheckTimeout: float
        :raise KafkaServerNotFound when no Kafka server responds
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
            
            # Create the thread that will listen to Kafka;
            # raises KafkaServerNotFound if necessary:
            waitThread = TopicWaiter(topicName, 
                                     self, 
                                     self.kafkaGroupId, 
                                     deliveryCallback=deliveryCallback, 
                                     eventObj=event,
                                     kafkaLiveCheckTimeout=kafkaLiveCheckTimeout)

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
 
    def mySubscriptions(self):
        return self.topicEvents.keys()
        
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
        

    def awaitSynchronousReturn(self, topicName, rawResult, msgOffset):
        '''
        A callback for TopicWaiter. Invoked from a different thread!!
        This callback is installed by publish() when a synchronous
        bus 'call' is executed. The main thread, i.e. publish() will
        have delivered the request to the bus, and initialized the 
        following instance variables for us:

          * self.uuidToWaitFor: the message id an incoming result must have
          * self.syncResultError: a place for this method to place an error message if necessary
          * self.resultArrivedEvent: a threading.Event() obj which this method will set() when it's done.
        
        :param topicName: name of topic on which a message arrived
        :type topicName: string
        :param rawResult: message payload; a JSON string
        :type rawResult: string
        :param msgOffset: offset in Kafka system
        :type msgOffset: int
        '''
        
        # If this incoming message is the wrong topic,
        # ignore; this should never happen, b/c this method
        # is only installed as a listener when we hang for
        # a synchronous call:

        if topicName != self.topicToWaitFor:
            return
        
        # Turn msg JSON into a dict:
        try:
            thisResDict = json.loads(rawResult)
        except ValueError:
            self.syncResultError = 'Bad JSON while waiting for sync response: %s' % rawResult
            # Tell main thread that answer to synchronous
            # call arrived, and was processed:
            self.resultArrivedEvent.set()
            return
        
        # Is this a response msg, and is it the one
        # we are waiting for?
        thisUuid    = thisResDict.get('id', None)
        thisMsgType = thisResDict.get('type', None)
        thisContent = thisResDict.get('content', None)
        
        if thisUuid    == self.uuidToWaitFor and \
           thisMsgType == 'resp':
            # All good; store just the msg content field
            # in a result dict that's shared with the main
            # thread:
            self.resDict[thisUuid] = thisContent
        
            # Tell main thread that answer to synchronous
            # call arrived, and was processed:
            self.resultArrivedEvent.set()
        else:
            # Not the msg we are waiting for:
            return
    
    
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
        
        formatter = logging.Formatter(fmt='%(asctime)s-%(name)s-%(levelname)s-%(module)s: %(message)s',datefmt=None)
        
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


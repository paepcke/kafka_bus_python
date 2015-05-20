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

    def awaitTopic(self, topicName, deliveryCallback=None, block=False,  timeout=None):
        '''
        Fork a new thread that keeps waiting for any messages
        on the topic of the given name. If timeout is 
        
        :param topicName: official name of topic to listen for.
        :type topicName: string
        :param block: if True, will block  
        :type block: boolean
        :param timeout:
        :type timeout:
        '''
        waitThread = TopicWaiter(topicName, self)
        if block:
            waitThread.join(timeout)
            # Determine whether thread terminated, or timeout occurred:
            if waitThread.isAlive():
                return False
            else:
                return True
        return True
    
    def deliverResult(self, rawResult):
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
    
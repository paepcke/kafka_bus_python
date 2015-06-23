import functools
import sys
import time
import json

import kafka
from kafka_bus import BusAdapter

#TODO: Simulated grader ScoreResponder takes messages with format:
#  uid: String
#  score: Integer
# ScoreResponder converts score to a value between 0 and 1 and republishes
# a response message on the same topic (with the same msgID).

class ScoreResponder(object):

    DEFAULT_TOPIC = 'helloworld'

    def __init__(self, topicName=None):
        '''
        BusAdapter instance subscribes to topic and republishes
        on same topic when messages are received.
        '''

        # Initialize with client-provided or default topic
        if topicName is None:
            self.topicName = ScoreResponder.DEFAULT_TOPIC
        else:
            self.topicName = topicName

        # Curry callback function
        self.callback = functools.partial(self.echoGrade)

        # Instantiate BusAdapter and register topic and callback.
        self.bus = BusAdapter()
        self.bus.subscribeToTopic(self.topicName, self.callback)

        # Wait for upbus message
        while True:
            self.bus.waitForMessage(self.topicName)

    def echoGrade(self, topicName, msgText, msgOffset):
        '''
        Callback method for subscription to bus topic. Transforms scores in
        range [0, 100] to floating point values in [0, 1].
        '''

        # Load request to dict
        req = json.loads(msgText)

        # Ensure request is of correct type
        reqType = req['type']
        if reqType != 'req':
            return

        # Fetch request ID and message content
        reqID = req['id']
        msg = req['content']

        # Get uid and pop score from message
        uid = msg['uid']
        score = msg.pop('score')

        # Transform score to grade and push onto msg array
        grade = '%s' % float('%.2g' % score/100)
        msg['grade'] = grade

        # Republish message on same topic
        self.bus.publish(msg, self.topicName, msgType='resp', msgId=reqId)


if __name__ == '__main__':
    if (len(sys.argv1) > 1):
        topic = sys.argv[1]
        ScoreResponder(topic)
    else:
        ScoreResponder()

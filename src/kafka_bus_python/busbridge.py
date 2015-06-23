import sys
import json

from flask import Flask
from flask import request
from flask import render_template

import kafka
from kafka_bus import BusAdapter


# Initialize topic
DEFAULT_TOPIC = 'helloworld'
if (len(sys.argv) > 1):
    topic = sys.argv[1]
else:
    topic = DEFAULT_TOPIC

# Initialize bus
bus = BusAdapter()

# Initialize Flask frontend
app = Flask(__name__)


@app.route("/bus_test", methods=['GET', 'POST'])
def busInterface():
    # GET: Serve UI to client
    if request.method == 'GET':
        return render_template('index.html')

    # POST: Publish request data on bus, wait for synchronous response
    # Returns response from downbus module
    elif request.method == 'POST':
        req = request.data
        resp = bus.publish(json.loads(req), topicName=topic, sync=True)
        return resp

    # Other HTTP requests should fail
    else:
        print "Erroneous request sent to bus-HTTP interface."


if __name__ == '__main__':
    app.run(debug=True)

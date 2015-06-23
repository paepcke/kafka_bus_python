import sys

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
    if request.method == 'GET':
        bus.subscribeToTopic(topic)
        return render_template('index.html') #TODO: How to print out from sub msgs?
    elif request.method == 'POST':
        msg = request.form
        bus.publish(msg, topic)
        return "Published to topic." #IDEA: This could inject something useful
    else:
        print "Erroneous request sent to bus-HTTP interface."


if __name__ == '__main__':
    app.run(debug=True)

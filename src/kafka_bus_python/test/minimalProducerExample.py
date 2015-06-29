
from kafka_bus_python.kafka_bus import BusAdapter


if __name__ == '__main__':
    bus = BusAdapter()
    while True:
        # Read one line from console:
        msgText = raw_input("Type a message to send: ('Q' to end.): ")
        if msgText == 'Q':
            break
        else:
            bus.publish(msgText, 'exampleTopic')

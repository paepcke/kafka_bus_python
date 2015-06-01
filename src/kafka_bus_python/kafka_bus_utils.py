'''
Created on May 31, 2015

@author: paepcke
'''
import cStringIO
import functools
import json


#----------------------------------- Extension to json.JSONEncoder -------------------

class JSONEncoderBusExtended(json.JSONEncoder):
    
    # Partial function to use by clients of this library
    # when specifying the 'default' keyword value to
    # their json.dump(), and json.dumps() calls.
    # This value will be filled in a top-level
    # statement below, outside the class def, b/c
    # the JSONEncoderBusExtended class isn't defined
    # yet at this point: 
    jsonEncodeMethod = None

    @classmethod
    def default(self, objToJSONize):
        try:
            return(objToJSONize.isoformat())
        except Exception:
            # Let the base class default method raise the TypeError
            return json.JSONEncoder.default(self, objToJSONize)    

    @classmethod
    def makeJSON(self, pythonStructure):
        '''
        Turns a Python structure into JSON.
        
        :param pythonStructure: structure to convert
        :type pythonStructure: any
        :return JSON
        :rtype string
        :raise TypeError if structure contains JSONizable elements.
        '''
        io = cStringIO.StringIO()
        # JSON-encode the given Python structure,
        # using an JSONEncoder class extension
        # from kafka_bus_utils; it knows how to 
        # JSONize datetime objects.
        json.dump(pythonStructure, io, default=JSONEncoderBusExtended.default)
        val = io.getvalue()
        io.close()
        return val


JSONEncoderBusExtended.jsonEncodeMethod = functools.partial(JSONEncoderBusExtended.default)

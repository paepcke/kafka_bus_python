'''
Created on May 19, 2015

@author: paepcke
'''

class BusMessage(object):
    '''
    classdocs
    '''


    def __init__(self, pythonStruct, topicName=None):
        '''
        Constructor
        '''
        self.setContent(pythonStruct)
        self.topicName = None
        
    def setContent(self, pythonStruct):
        serialStruct = str(pythonStruct)
        self.content = serialStruct.encode('UTF-8', 'ignore')
        # Remember the raw object:
        self.rawContent = pythonStruct
        
    def content(self):
        return self.content
    
    def rawContent(self):
        return self.rawContent
    
    def topicName(self):
        return self.topicName
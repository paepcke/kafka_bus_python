'''
Created on May 19, 2015

@author: paepcke
'''

class BusTopic(object):
    '''
    classdocs
    '''


    def __init__(self, name, pythonStruct=None):
        '''
        Constructor
        '''
        self.name = name
        self.setContent(pythonStruct)
        
    def setContent(self, pythonStruct):
        serialStruct = str(pythonStruct)
        self.content = serialStruct
        
    def content(self):
        return self.content
    
    
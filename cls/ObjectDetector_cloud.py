#!/usr/bin/env python

import os, logging
import threading

from cls.ObjectDetectorBase import ObjectDetectorBase

class ObjectDetector_cloud(ObjectDetectorBase):
    """ Object Detection using remote cloud server. Can be used if there is no enought local CPU/GPU power available
    """
    def __init__(self, cnfg, logger_name='None'):
        ObjectDetectorBase.__init__(self, cnfg, logger_name)

    def detect(self, filename):
        """ Publish image for object detection into cloud. Using separate thread.
        """
        self.publish(filename) 

    def publish(self, filename):
        """ This method encrypts file, publish it to remote server and wait for the result.
        """
        # 1) Encrypt file
        # 2) Publish to remote cloud server
        # 3) Wait for the result
        # 4) Store results in files located inside RAM folder
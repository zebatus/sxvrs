#!/usr/bin/env python

import os, logging
import threading

from cls.ObjectDetectorBase import ObjectDetectorBase

class ObjectDetector_local(ObjectDetectorBase):
    """ Object Detection using local CPU or GPU. Make sure that you have enought CPU/GPU available, otherwice use cloud detection
    """
    def __init__(self, cnfg):
        ObjectDetectorBase.__init__(self, cnfg)

    def detect(self, filename):
        """ Object Detection using CPU or GPU
        """
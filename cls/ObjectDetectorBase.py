#!/usr/bin/env python

import os, logging
import glob
from abc import ABC

from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage
from cls.ObjectDetector_cloud import ObjectDetector_cloud
from cls.ObjectDetector_local import ObjectDetector_local

class ObjectDetectorBase():
    """ Base class for object detection. Must be inherited by <local> and <cloud> versions
    """
    def __init__(self, cnfg):
        self.cnfg = cnfg
        # Mount RAM storage disk
        self.ram_storage = RAM_Storage(cnfg)
        # Create storage manager
        self.storage = StorageManager(cnfg.storage_path(), cnfg.storage_max_size)
    
    def detect(self, filename):
        """ Abstract method, must be implementet inside derived classes
        """
        return NotImplemented

    def scan_waiting_files(self):
        """ This function scans RAM folder to look for the images ready for ObjectDetection (i.e. .obj.wait extension)
        """
        img_list = self.storage.get_file_list(f"{self.ram_storage.storage_path}/*.obj.wait")
        for filename_wait in img_list:
            filename_start = f"{filename_wait[:-5]}.start"
            os.rename(filename_wait, filename_start)
            self.detect(filename_start)

def SelectObjectDetector(cnfg):
    """ This function selects required ObjectDetector based on config value 
    """
    use_cloud = cnfg['']
    if use_cloud:
        return ObjectDetector_cloud(cnfg)
    else:
        return ObjectDetector_local(cnfg)

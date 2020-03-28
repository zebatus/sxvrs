#!/usr/bin/env python

import os, logging
import glob
import time

from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage

class ObjectDetectorBase():
    """ Base class for object detection. Must be inherited by <local> and <cloud> versions
    """
    def __init__(self, cnfg, logger_name='None'):
        self.logger = logging.getLogger(f"{logger_name}:ObjectDetector")
        self.cnfg = cnfg
        self.is_started = False
        # Mount RAM storage disk
        self.ram_storage = RAM_Storage(cnfg)
        # Create storage manager
        self.storage = StorageManager(cnfg.temp_storage_path, cnfg.temp_storage_size, logger_name = self.logger.name)

    def start(self):
        """ This function for running main loop: scan folder for files and start processing them
        """
        if self.is_started:
            self.logger.error('Object detector is already started')
            return
        self.is_started = True
        while True:
            filename = self.storage.get_first_file(f"{self.ram_storage.storage_path}/*.obj.wait")
            if filename is None:
                sleep_time = 1
                self.logger.debug(f'No new files for object detection. Sleep {sleep_time} sec')
                time.sleep(sleep_time)
                continue
            if filename[-9:] == ".obj.wait":
                self.logger.debug(f"ObjectDetector: Found file: {filename}")
                filename_start = f"{filename[:-5]}.start"
                os.rename(filename, filename_start)
                self.detect(filename_start)

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



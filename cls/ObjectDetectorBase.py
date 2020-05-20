#!/usr/bin/env python

import os, logging
import glob
import time
from threading import Thread, Event

from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage

class ObjectDetectorBase():
    """ Base class for object detection. Must be inherited by <local> and <cloud> versions
    """
    def __init__(self, cnfg, logger_name='None'):
        self.logger = logging.getLogger(f"{logger_name}:ObjectDetector")
        self.cnfg = cnfg
        self._stop_event = Event()
        self._stop_event.set()
        # Mount RAM storage disk
        self.ram_storage = RAM_Storage(cnfg)
        # Create storage manager
        self.storage = StorageManager(cnfg.temp_storage_path, cnfg.temp_storage_size, logger_name = self.logger.name)

    def is_started(self):
        return not self._stop_event.is_set()

    def thread_watch(self):
        """ Watch folder and wait for new files
        """
        sleep_time = self.cnfg.object_detector_sleep_time
        while not self._stop_event.is_set():
            try:
                filename = self.storage.get_first_file(f"{self.ram_storage.storage_path}/*.obj.wait", 
                                                        start_mtime= time.time() - self.cnfg.object_detector_timeout + 2 # do not take outdated files ( +2 sec to be safe)
                                                        )
                if filename is None:                    
                    #self.logger.debug(f'Wait for file. Sleep {sleep_time} sec')
                    time.sleep(sleep_time)
                    continue
                if filename[-9:] == ".obj.wait":
                    self.logger.debug(f"ObjectDetector: Found file: {filename}")
                    filename_start = f"{filename[:-5]}.start"
                    os.rename(filename, filename_start)
                    self.detect(filename_start)
            except:
                self.logger.exception(f"Object Detection Error: {filename}")

    def start_watch(self):
        """ This function for running main loop: scan folder for files and start processing them
        """
        if not self._stop_event.is_set():
            self.logger.error('Object detector is already started')
            return
        self._stop_event.clear()
        self.thread = Thread(target=self.thread_watch, args=())
        self.thread.start()
        self.logger.debug("ObjectDetector start folder watching")

    def detect(self, filename):
        """ Abstract method, must be implementet inside derived classes
        """
        return NotImplemented
    
    def stop_watch(self):
        """ Abstract method, must be implementet inside derived classes
        """
        if not self.thread is None:
            self._stop_event.set()
            self.thread.join()
            self.logger.debug("ObjectDetector stop folder watching")
        return True

    def scan_waiting_files(self):
        """ This function scans RAM folder to look for the images ready for ObjectDetection (i.e. .obj.wait extension)
        """
        img_list = self.storage.get_file_list(f"{self.ram_storage.storage_path}/*.obj.wait")
        for filename_wait in img_list:
            filename_start = f"{filename_wait[:-5]}.start"
            os.rename(filename_wait, filename_start)
            self.detect(filename_start)



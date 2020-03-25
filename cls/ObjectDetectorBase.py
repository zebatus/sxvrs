#!/usr/bin/env python

# dependency: pip install watchdog

import os, logging
import glob
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage

class ObjectDetectorBase():
    """ Base class for object detection. Must be inherited by <local> and <cloud> versions
    """
    def __init__(self, cnfg, logger_name='None'):
        self.logger = logging.getLogger(f"{logger_name}:ObjectDetector")
        logging.getLogger("watchdog").setLevel(logging.ERROR)
        self.cnfg = cnfg
        # Mount RAM storage disk
        self.ram_storage = RAM_Storage(cnfg)
        # Create storage manager
        self.storage = StorageManager(cnfg.temp_storage_path, cnfg.temp_storage_size, logger_name = self.logger.name)
        # Create wachdog observer for folder monitoring
        patterns = "*.obj.wait"
        ignore_patterns = ""
        ignore_directories = True
        case_sensitive = True
        event_handler = PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive)
        event_handler.on_created = self.on_file_available
        event_handler.on_moved = self.on_file_available        
        self.observer = Observer()
        self.observer.schedule(event_handler, f"{self.ram_storage.storage_path}/")

    def on_file_available(self, event):
        self.logger.debug(f"Watchdog: Found file {event.src_path}")
        filename_wait = event.src_path
        filename_start = f"{filename_wait[:-5]}.start"
        os.rename(filename_wait, filename_start)
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
    
    def start(self):
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()


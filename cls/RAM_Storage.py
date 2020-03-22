#!/usr/bin/env python

import os
import logging
from subprocess import Popen

class RAM_Storage():
    """ RAM storage disk for fast file exchange between processes    
    """
    def __init__(self, cnfg, logger_name='None'):
        self.logger = logging.getLogger(f"{logger_name}:RAM_Storage")
        self.storage_path = cnfg.temp_storage_path
        self.storage_size = cnfg.temp_storage_size
        self.cmd_mount = cnfg.temp_storage_cmd_mount
        self.cmd_unmount = cnfg._temp_storage_cmd_unmount
        self.mount()
    
    def mount(self):
        if not os.path.isdir(self.storage_path):
            Popen(self.cmd_mount, shell=True)

    def unmount(self):
        if os.path.isdir(self.storage_path):
            Popen(self.cmd_unmount, shell=True)

    

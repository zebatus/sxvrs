#!/usr/bin/env python

"""     Simple eXtendable Watcher Script
Main features:
    1) Monitor provided RAM folder and take frame
    2) Motion Detection between taken frames
    3) Run object detection if motion detected
    4) Remember for some time all detected object
    5) Take an action on frame where object was detected (email, copy, etc..)

Usage:
    python sxvrs_watcher -n <name>
"""

__author__      = "Rustem Sharipov"
__copyright__   = "Copyright 2020"
__license__     = "GPL"
__version__     = "0.2.0"
__maintainer__  = "Rustem Sharipov"
__email__       = "zebatus@gmail.com"
__status__      = "Development"

import os, sys, logging
from subprocess import Popen, PIPE, STDOUT
import yaml
import json
import time
from datetime import datetime
import argparse
import shutil
from threading import Thread

from cls.config_reader import config_reader
from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage
from cls.MotionDetector import MotionDetector
from cls.ActionManager import ActionManager

# Get command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('-n','--name', help='Name of the recorder instance', required=True)
parser.add_argument('-fw','--frame_width', help='The width of the video frames in source stream', required=False)
parser.add_argument('-fh','--frame_height', help='The height of the video frames in source stream', required=False)
parser.add_argument('-fd','--frame_dim', help='The number of dimensions of the video frames in source stream. (By default = 3)', required=False, default=3)
#parser.add_argument('-','--', help='', default='default', required=False)
args = parser.parse_args()
_name = args.name
try:
    _frame_width = int(args.frame_width)
    _frame_height = int(args.frame_height)
    _frame_dim = int(args.frame_dim)
except:
    _frame_width = None
    _frame_height = None
    _frame_dim = 3

# Get running script name
script_path, script_name = os.path.split(os.path.splitext(__file__)[0])
app_label = script_name + f'_{datetime.now():%H%M}'
dt_start = datetime.now()

# Load configuration files
cnfg_daemon = config_reader(
        os.path.join('cnfg' ,'sxvrs.yaml'), 
        log_filename = f'watcher_{_name}'
    )
logger = logging.getLogger(f"{script_name}:{_name}")
logger.debug(f"> Start on: '{dt_start}'")
if _name in cnfg_daemon.recorders:
    cnfg = cnfg_daemon.recorders[_name]
else:
    msg = f"Recorder '{_name}' not found in config"
    logger.error(msg)
    raise ValueError(msg)

# Mount RAM storage disk
ram_storage = RAM_Storage(cnfg_daemon, logger_name = logger.name)

# Create storage manager
storage = StorageManager(cnfg.storage_path(), cnfg.storage_max_size, logger_name = logger.name)

# Create MotionDetector
motion_detector = MotionDetector(cnfg, logger_name = logger.name)

# Create ActionManager to run actions on files with detected objects
action_manager = ActionManager(cnfg, logger_name = logger.name)

while True:
    try:
        filename = storage.get_first_file(f"{ram_storage.storage_path}/{_name}_*.rec")
        if filename is None:
            sleep_time = 1
            logger.debug(f'No new files for motion detection. Sleep {sleep_time} sec')
            time.sleep(sleep_time)
            continue
        filename_wch = f"{filename[:-4]}.wch"
        os.rename(filename, filename_wch)
        is_motion = motion_detector.detect(filename_wch)
        if cnfg_daemon.is_object_detection:
            if is_motion:
                os.rename(filename_wch, f"{filename[:-4]}.obj.wait")
            else:
                os.remove(filename_wch)
            # look for all files where object detection is complete
            obj_none_list = storage.get_file_list(f"{ram_storage.storage_path}/{_name}_*.obj.none")
            for filename_obj_none in obj_none_list:
                os.remove(filename_obj_none)
            obj_found_list = storage.get_file_list(f"{ram_storage.storage_path}/{_name}_*.obj.found")
            for filename_obj_found in obj_found_list:
                # Read info file
                with open(filename_obj_found+'.info') as f:
                    info = json.load(f)
                # Take actions on image where objects was found
                action_manager.run(filename_obj_found, info) 
                # Remove temporary file
                os.remove(filename_obj_found+'.info')
                os.remove(filename_obj_found)
        else: # in case if object detection is dissabled
            # TODO: notify recorder that object detected
            os.remove(filename_wch)
    except (KeyboardInterrupt, SystemExit):
        logger.info("[CTRL+C detected]")
        break
    except:
        logger.exception(f"watcher '{_name}'")

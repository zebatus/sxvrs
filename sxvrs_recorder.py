#!/usr/bin/env python

"""     SXVRS Recorder
This script connects to video source stream, for taking snapshots, motion detection and video recording
Main features:
    1) take snapshot from video source
    2) record into file
    3) detect motion by comparing snapshots

Dependencies:
     ffmpeg
"""

__author__      = "Rustem Sharipov"
__copyright__   = "Copyright 2020"
__license__     = "GPL"
__version__     = "0.2.0"
__maintainer__  = "Rustem Sharipov"
__email__       = "zebatus@gmail.com"
__status__      = "Development"

import os, sys, logging
import argparse
import numpy as np
import cv2
from subprocess import Popen, PIPE
from datetime import datetime
from time import time
from cls.config_reader import config_reader
from cls.misc import get_frame_shape
from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage

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
        log_filename = f'recorder_{_name}'
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

# calculate frame_size
if _frame_width is None or _frame_height is None or _frame_dim is None:
    frame_shape = get_frame_shape(cnfg.stream_url())
else:
    frame_shape = (_frame_height, _frame_width, _frame_dim)
frame_size = frame_shape[0] * frame_shape[1] * frame_shape[2]
logger.debug(f"frame_shape = {frame_shape}     frame_size = {frame_size}")

# Maintain Storage for the recorded files:
storage = StorageManager(cnfg.storage_path(), cnfg.storage_max_size, logger_name = logger.name)
storage.cleanup()
# Force create path for snapshot
storage.force_create_file_path(cnfg.filename_snapshot())
# Force create path for video file
filename_video = cnfg.filename_video()
storage.force_create_file_path(filename_video)

cmd_ffmpeg_read = cnfg.cmd_ffmpeg_read()
logger.debug(f"Execute process to read frames:\n   {cmd_ffmpeg_read}")
ffmpeg_read = Popen(cmd_ffmpeg_read, shell=True, stdout = PIPE, bufsize=frame_size*cnfg.ffmpeg_buffer_frames)
cmd_ffmpeg_write = cnfg.cmd_ffmpeg_write(filename=filename_video, height=frame_shape[0], width=frame_shape[1], pixbytes=frame_shape[2]*8)
if not cmd_ffmpeg_write is None:
    logger.debug(f"Execute process to write frames:\n  {cmd_ffmpeg_write}")
    ffmpeg_write = Popen(cmd_ffmpeg_write, shell=True, stderr=None, stdout=None, stdin = PIPE, bufsize=frame_size*cnfg.ffmpeg_buffer_frames)
snapshot_taken_time = 0
i = 0
throttling = 0
while True:
    frame_bytes = ffmpeg_read.stdout.read(frame_size)
    if len(frame_bytes)==0:
        logging.error("Received zero length frame. exiting recording loop..")
        break
    frame_np = (np.frombuffer(frame_bytes, np.uint8).reshape(frame_shape)) 
    # take snapshot
    if time() - snapshot_taken_time > cnfg.snapshot_time:
        frame_np = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
        cv2.imwrite(cnfg.filename_snapshot(), frame_np)
        snapshot_taken_time = time()
    # process frame in RAM folder
    if cnfg.is_motion_detection and (i % (cnfg.frame_skip + throttling) == 0):
        # check for throttling
        tmp_size = storage.get_folder_size(ram_storage.storage_path, f'{cnfg.name}_*')
        if tmp_size > cnfg.throttling_max_mem_size:
            throttling += throttling + 5
            logger.error(f"Can't save frame to temporary RAM folder. There are too many files for recorder: {cnfg.name}.\n Size occupied: {tmp_size}\n Max size: {cnfg.throttling_max_mem_size}")
        elif tmp_size > cnfg.throttling_min_mem_size:
            throttling += throttling + 2
            logger.warning(f"Start frame throttling ({throttling}) for recorder: {cnfg.name}")
        else:
            throttling = 0
        if tmp_size < cnfg.throttling_max_mem_size:
            # save frame into RAM snapshot file
            frame_np_rgb = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
            temp_frame_file = cnfg.filename_temp(storage_path=ram_storage.storage_path)
            cv2.imwrite(f'{temp_frame_file}.bmp', frame_np_rgb)
            os.rename(f'{temp_frame_file}.bmp', f'{temp_frame_file}.rec')
    # save frame to video file
    if not ffmpeg_write is None:
        ffmpeg_write.stdin.write(frame_np.tostring())
    dt_end = datetime.now()
    if (dt_end - dt_start).total_seconds() >= cnfg.record_time:
        break
    i += 1
logger.debug(f"> Finish on: '{dt_end}'")
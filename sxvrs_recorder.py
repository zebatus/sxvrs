#!/usr/bin/env python

"""     SXVRS Recorder
This script connects to video source stream, Continuously takes snapshots and record into video file.
It is possible to run script in snapshot_mode - meaning no video recording is done, only snapshots are taken

Dependencies:
     ffmpeg

Starting parameters:
    > python sxvrs_recorder.py -n <recorder_name> -fw <frame_width> -fh <frame_height> fd <frame_dimentions> --snapshot_mode

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
import signal
import shlex
import hashlib
import math
# interacting with proc by keypress events
from threading import Thread, Event
import select

from cls.config_reader import config_reader
from cls.misc import get_frame_shape
from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage

# Get command line arguments
arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('-n','--name', help='Name of the recorder instance', required=True)
arg_parser.add_argument('-fw','--frame_width', help='The width of the video frames in source stream', required=False)
arg_parser.add_argument('-fh','--frame_height', help='The height of the video frames in source stream', required=False)
arg_parser.add_argument('-fc','--frame_channels', help='The number of channels of the video frames in source stream. (By default = 3)', required=False, default=3)
arg_parser.add_argument('-s','--snapshot_mode', help='Determine if only snapshots must be taken, without recording video file', action='store_true')
#arg_parser.add_argument('-','--', help='', default='default', required=False)
args = arg_parser.parse_args()
_name = args.name
try:
    _frame_width = int(args.frame_width)
    _frame_height = int(args.frame_height)
    _frame_ch = int(args.frame_channels)    
except:
    _frame_width = None
    _frame_height = None
    _frame_ch = 3
snapshot_mode = args.snapshot_mode

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
if _frame_width is None or _frame_height is None or _frame_ch is None:
    _frame_height, _frame_width, _frame_ch = get_frame_shape(cnfg.stream_url())
frame_size = _frame_height * _frame_width * _frame_ch
logger.debug(f"frame_shape = ({_frame_height}, {_frame_width}, {_frame_ch})    frame_size = {frame_size}")
# calculate resized values (if it is needed to resize)
if cnfg.resize_frame:
    if _frame_height > cnfg.resize_frame_height:
        scale_height = cnfg.resize_frame_height / _frame_height
    else:
        scale_height = 1
    if _frame_width > cnfg.resize_frame_width:
        scale_width = cnfg.resize_frame_width / _frame_width
    else:
        scale_width = 1
    scale = min(scale_height, scale_width) 
    new_height = round(_frame_height * scale)
    new_width = round(_frame_width * scale)
else:
    scale = 1
# Maintain Storage for the recorded files:
storage = StorageManager(cnfg.storage_path(), cnfg.storage_max_size, logger_name = logger.name)
storage.cleanup()
# Force create path for snapshot
storage.force_create_file_path(cnfg.filename_snapshot())
# event to detect if watcher is started
_stop_event = Event() 
_watcher_started_event = Event() 
if cnfg.is_motion_detection:
    _watcher_started_event.set()
def handle_keypress():
    while not _stop_event.is_set():
        rfds, wfds, efds = select.select( [sys.stdin], [], [], 2)
        if rfds:
            char = sys.stdin.read(1)
            #print('> '*20+f'pressed: {char}')
            if char == 'w':
                _watcher_started_event.set()
            elif char == 'e':
                _watcher_started_event.clear()
thread_handle_keypress = Thread(target=handle_keypress)
thread_handle_keypress.start()
# correct termination on signal receive
def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    _stop_event.set()
signal.signal(signal.SIGINT, signal_handler)

cmd_ffmpeg_read = cnfg.cmd_ffmpeg_read()
logger.debug(f"Execute process to read frames:\n   {cmd_ffmpeg_read}")
ffmpeg_read = Popen(shlex.split(cmd_ffmpeg_read), stdout = PIPE, bufsize=frame_size*cnfg.ffmpeg_buffer_frames)
if snapshot_mode:
    logger.debug("Snapshot mode detected: continuously take snapshots from source stream")
    cmd_ffmpeg_write = None
else:
    # Force create path for video file
    filename_video = cnfg.filename_video()
    storage.force_create_file_path(filename_video)
    logger.info(f'Start record filename: <{filename_video}>')
    if scale != 1:
        cmd_ffmpeg_write = cnfg.cmd_ffmpeg_write(filename=filename_video, height=new_height, width=new_width, pixbytes=_frame_ch*8)
    else:
        cmd_ffmpeg_write = cnfg.cmd_ffmpeg_write(filename=filename_video, height=_frame_height, width=_frame_width, pixbytes=_frame_ch*8)
if not cmd_ffmpeg_write is None and not snapshot_mode:
    logger.debug(f"Execute process to write frames:\n  {cmd_ffmpeg_write}")
    ffmpeg_write = Popen(shlex.split(cmd_ffmpeg_write), stderr=None, stdout=None, stdin = PIPE, bufsize=frame_size*cnfg.ffmpeg_buffer_frames)
else:
    ffmpeg_write = None
try:
    snapshot_taken_time = 0
    i = 0
    snap = 0
    throttling = 0
    frame_hash_old = ''
    compare_frame_width = None
    while not _stop_event.is_set() and ((not snapshot_mode) or (snapshot_mode and _watcher_started_event.is_set)):
        frame_bytes = ffmpeg_read.stdout.read(frame_size)
        if len(frame_bytes)==0:
            logging.error("Received zero length frame. exiting recording loop..")
            break
        frame_np = (np.frombuffer(frame_bytes, np.uint8).reshape((_frame_height, _frame_width, _frame_ch))) 
        # resize frame if needed
        if scale != 1:
            frame_np = cv2.resize(frame_np, (new_width, new_height))  
        # take snapshot
        if time() - snapshot_taken_time > cnfg.snapshot_time:
            frame_np_rgb = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
            filename_snapshot = cnfg.filename_snapshot()
            logger.info(f'Snapshot filename: <{filename_snapshot}>')
            cv2.imwrite(filename_snapshot, frame_np_rgb)
            snapshot_taken_time = time()
        # process frame in RAM folder
        if _watcher_started_event.is_set() and (i % (cnfg.frame_skip + throttling) == 0):
            # check for throttling
            tmp_size = storage.get_folder_size(ram_storage.storage_path, f'{cnfg.name}_*')
            if tmp_size > cnfg.throttling_max_mem_size:
                throttling += 10
                logger.error(f"Can't save frame to temporary RAM folder. There are too many files for recorder: {cnfg.name}.\n Size occupied: {tmp_size}\n Max size: {cnfg.throttling_max_mem_size}")
            elif tmp_size > cnfg.throttling_min_mem_size:
                throttling += 1
                logger.warning(f"Start frame throttling ({throttling}) for recorder: {cnfg.name}")
            else:
                if throttling>0:
                    throttling = 0
                    logger.warning(f"No frame throttling ({throttling}) for recorder: {cnfg.name}")                
            if tmp_size < cnfg.throttling_max_mem_size:
                # Need to compare hash of the frame to detect duplicated frames
                # but first, make frame significantly smaller (like simple motion detection)
                if compare_frame_width is None:
                    height, width, channels = frame_np.shape
                    compare_scale = cnfg.frame_comparing_width / width
                    compare_frame_width = math.floor(width * compare_scale)
                    compare_frame_height = math.floor(height * compare_scale)
                frame_compare = cv2.resize(frame_np, (compare_frame_width, compare_frame_height))
                frame_hash = hashlib.sha1(frame_compare).hexdigest()
                if frame_hash != frame_hash_old:
                    frame_hash_old = frame_hash
                    temp_frame_file = cnfg.filename_temp(storage_path=ram_storage.storage_path, frame_num=i)
                    # save frame into RAM snapshot file
                    frame_np_rgb = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)                    
                    cv2.imwrite(f'{temp_frame_file}.bmp', frame_np_rgb)
                    os.rename(f'{temp_frame_file}.bmp', f'{temp_frame_file}.rec')
                    snap += 1
        # save frame to video file
        if not ffmpeg_write is None:
            ffmpeg_write.stdin.write(frame_np.tostring())       
        dt_end = datetime.now() 
        if (dt_end - dt_start).total_seconds() >= cnfg.record_time:
            break
        i += 1
    if not snapshot_mode:
        logger.debug(f"Finish recording to {filename_video} wrote {i}/{snap} frames")
except (KeyboardInterrupt, SystemExit):
    logger.info("[CTRL+C detected] MainLoop")
_stop_event.set()
if not ffmpeg_write is None:
    ffmpeg_write.send_signal(signal.SIGINT)
if not ffmpeg_read is None:
    ffmpeg_read.send_signal(signal.SIGINT)
dt_end = datetime.now()
logger.debug(f"> Finish on: '{dt_end}'")
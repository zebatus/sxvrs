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
from cls.config_reader import config_reader
from cls.misc import get_frame_shape

# Get command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('-n','--name', help='Name of the recorder instance', required=True)
parser.add_argument('-fw','--frame_width', help='The width of the video frames in source stream', required=False)
parser.add_argument('-fh','--frame_height', help='The height of the video frames in source stream', required=False)
parser.add_argument('-fd','--frame_dim', help='The number of dimensions of the video frames in source stream. (By default = 3)', required=False, default=3)
#parser.add_argument('-','--', help='', default='default', required=False)
args = parser.parse_args()
_name = args.name
_frame_width = int(args.frame_width)
_frame_height = int(args.frame_height)
_frame_dim = int(args.frame_dim)

# Get running script name
script_path, script_name = os.path.split(os.path.splitext(__file__)[0])
app_label = script_name + f'_{datetime.now():%H%M}'

logger = logging.getLogger(_name)
logging.debug(f"> Start on: '{datetime}'")

# Load configuration files
cnfg_daemon = config_reader(os.path.join('cnfg' ,'sxvrs.yaml'))
if _name in cnfg_daemon.recorders:
    cnfg = cnfg_daemon.recorders[_name]
else:
    msg = f"Recorder '{_name}' not found in config"
    logging.error(msg)
    raise ValueError(msg)

# calculate frame_size
if _frame_width is None or _frame_height is None or _frame_dim is None:
    frame_shape = get_frame_shape(cnfg.stream_url)
else:
    frame_shape = (_frame_height, _frame_width, _frame_dim)
frame_size = frame_shape[0] * frame_shape[1] * frame_shape[2]
logging.debug(f"frame_shape = {frame_shape}     frame_size = {frame_size}")

def force_create_path(filename):
    path = os.path.dirname(filename)
    if not os.path.exists(path):
        logging.debug(f'path not existing: {path} \n try to create it..')
        try:
            os.makedirs(path)
        except:
            logging.exception(f'Can''t create path: {path}')
# Force create path for snapshot
force_create_path(cnfg.snapshot_filename())
# Force create path for video file
filename_video_out = cnfg.filename()
force_create_path(filename_video_out)

cmd_ffmpeg_read = cnfg.cmd_ffmpeg_read()
logging.debug(f"Execute process to read frames: {cmd_ffmpeg_read}")
ffmpeg_read = Popen(cmd_ffmpeg_read, shell=True, stdout = PIPE, bufsize=frame_size*cnfg.ffmpeg_buffer_frames)
cmd_ffmpeg_write = cnfg.cmd_ffmpeg_write(filename=filename_video_out, height=frame_shape[0], width=frame_shape[1], pixbytes=frame_shape[2]*8)
logging.debug(f"Execute process to write frames: {cmd_ffmpeg_write}")
ffmpeg_write = Popen(cmd_ffmpeg_write, shell=True, stdin = PIPE, bufsize=frame_size*cnfg.ffmpeg_buffer_frames)
i = 0
while True:
    frame_bytes = ffmpeg_read.stdout.read(frame_size)
    frame_np = (np.frombuffer(frame_bytes, np.uint8).reshape(frame_shape)) 
    # save frame to snapshot file
    cv2.imwrite(cnfg.snapshot_filename(), frame_np)
    # save frame to video file
    ffmpeg_write.stdin.write(frame_np.tostring())
    i += 1
    if i>100:
        break

logging.debug(f"> Finish on: '{datetime}'")
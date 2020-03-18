#!/usr/bin/env python

import cv2
import json
import subprocess as sp
from cls.ObjectDetector_cloud import ObjectDetector_cloud
from cls.ObjectDetector_local import ObjectDetector_local

def SelectObjectDetector(cnfg):
    """ This function selects required ObjectDetector based on config value 
    """
    if cnfg.is_object_detector_cloud:
        return ObjectDetector_cloud(cnfg)
    elif cnfg.is_object_detector_local:
        return ObjectDetector_local(cnfg)
    else:
        logging.warning('Object detection is not defined. Skipping..')

def get_frame_shape(source):
    ffprobe_cmd = " ".join([
        'ffprobe',
        '-v',
        'panic',
        '-show_error',
        '-show_streams',
        '-of',
        'json',
        '"'+source+'"'
    ])
    print(ffprobe_cmd)
    p = sp.Popen(ffprobe_cmd, stdout=sp.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()
    info = json.loads(output)
    print(info)

    video_info = [s for s in info['streams'] if s['codec_type'] == 'video'][0]

    if video_info['height'] != 0 and video_info['width'] != 0:
        return (video_info['height'], video_info['width'], 3)
    
    # fallback to using opencv if ffprobe didnt succeed
    video = cv2.VideoCapture(source)
    ret, frame = video.read()
    frame_shape = frame.shape
    video.release()
    return frame_shape

def check_topic(topic, value):
    return topic.lower().endswith(f"/{value}")
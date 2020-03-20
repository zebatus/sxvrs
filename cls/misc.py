#!/usr/bin/env python

import logging
import sys
import cv2
import json
import subprocess as sp

# Class for Recorder
class Recorder():
    def __init__(self, name):
        self.name = name
        self.status = 'None'
        self.error_cnt = 0 
        self.latest_file = ''
    
    def update(self, values):
        """ Function updates recorder values according on dictionary
        """
        if 'status' in values:
            self.status = values['status']
        if 'error_cnt' in values:
            self.error_cnt = values['error_cnt']
        if 'latest_file' in values:
            self.latest_file = values['latest_file']

def SelectObjectDetector(cnfg):
    """ This function selects required ObjectDetector based on config value 
    """
    if cnfg.is_object_detector_cloud:
        from cls.ObjectDetector_cloud import ObjectDetector_cloud
        return ObjectDetector_cloud(cnfg)
    elif cnfg.is_object_detector_local:
        if 'tensorflow' in sys.modules:
            from cls.ObjectDetector_local import ObjectDetector_local
            return ObjectDetector_local(cnfg)
        else:
            logging.error('Tensorflow is not installed. Using Object Detection by local CPU/GPU is not possible')
            return None
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
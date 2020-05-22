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
        self.record = False
        self.watcher = False
    
    def update(self, values):
        """ Function updates recorder values according on dictionary
        """
        self.status = values.get('status', self.status)
        self.record = values.get('record', self.record)
        self.watcher = values.get('watcher', self.watcher)
        self.error_cnt = values.get('error_cnt', self.error_cnt)
        self.latest_file = values.get('latest_file', self.latest_file)

def check_package_is_installed(name='tensorflow'):
    import importlib
    return importlib.util.find_spec(name) is not None

def SelectObjectDetector(cnfg, logger_name='None'):
    """ This function selects required ObjectDetector based on config value 
    """
    if cnfg.is_object_detector_cloud:
        from cls.ObjectDetector_cloud import ObjectDetector_cloud
        return ObjectDetector_cloud(cnfg, logger_name)
    elif cnfg.is_object_detector_local:
        if cnfg.tensorflow_is_installed:
            from cls.ObjectDetector_local import ObjectDetector_local
            return ObjectDetector_local(cnfg, logger_name)
        else:
            logging.error('Tensorflow is not installed. Using Object Detection by local CPU/GPU is not possible')
            return None
    else:
        logging.warning('Object detection is not defined. Skipping..')

def get_frame_shape(source):
    ffprobe_cmd = f'ffprobe -v panic -show_error -show_streams -of json "{source}"'
    logging.debug(ffprobe_cmd)
    p = sp.Popen(ffprobe_cmd, stdout=sp.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()
    info = json.loads(output)
    logging.debug(info)
    if 'error' in info:
        logging.warning(f'Can''t open {source}: {info}')
        #raise Exception(f'Can''t open {source}')
    else:
        video_info = [s for s in info['streams'] if s['codec_type'] == 'video'][0]

        if video_info['height'] != 0 and video_info['width'] != 0:
            return (video_info['height'], video_info['width'], 3)
        
        # fallback to using opencv if ffprobe didnt succeed
        try:
            video = cv2.VideoCapture(source)
            ret, frame = video.read()
            frame_shape = frame.shape
            video.release()
            return frame_shape
        except Exception as e:
            logging.warning(f'OpenCPV Can''t get frame shape: source= {source}')
            raise e

def check_topic(topic, value):
    return topic.lower().endswith(f"/{value}") or topic.lower().endswith(f"/*") 

def ping_ip(ip):
    try:
        sp.check_output(["ping", "-c", "1", ip])
        return True                      
    except sp.CalledProcessError:
        return False


# OrEvent ( https://stackoverflow.com/questions/12317940/python-threading-can-i-sleep-on-two-threading-events-simultaneously/36661113 )
""" Modified version: 
    1) can be used multuple times (as events modificated only once and using callback function list)
    2) If provided array of events have already triggered events, then discard them
"""
import threading

def notify_on_change(self):
    while len(self.on_change)>0:
        callback = self.on_change.pop()
        callback()

def or_set(self):
    self._set()
    notify_on_change(self)

def or_clear(self):
    self._clear()
    notify_on_change(self)

def orify(e, changed_callback):    
    if not hasattr(e, "_set"):
        e._set = e.set
        e._clear = e.clear
        e.on_change = []
        e.set = lambda: or_set(e)
        e.clear = lambda: or_clear(e)
    e.on_change.append(changed_callback)

def OrEvent(*events):
    or_event = threading.Event()
    def changed():
        bools = [e.is_set() for e in events]
        if any(bools):
            or_event.set()
        else:
            or_event.clear()
    for e in events:
        orify(e, changed)
    changed()
    return or_event

def AnyChangeEvent(*events):
    """Keep states of events, and fire when any event is changed 
    (from _flag=True to Flase and vice versa)
    """
    or_event = threading.Event()
    events_state = {}
    for e in events:
        events_state[id(e)] = e.is_set()
    def changed():
        bools = [(e.is_set() !=  events_state[id(e)]) for e in events]
        if any(bools):
            or_event.set()
        else:
            or_event.clear()
    for e in events:
        orify(e, changed)
    changed()
    return or_event
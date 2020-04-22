#!/usr/bin/env python

""" Camera Instance
It runs separate thread for recording in a loop and run additional separate thread for watcher loop
"""
import os
import logging
import json
from datetime import datetime
import time
from threading import Thread, Event
import subprocess
from operator import itemgetter
import math
import signal

from cls.misc import get_frame_shape, ping_ip
from cls.config_reader import config_reader
from cls.StorageManager import StorageManager
from cls.RAM_Storage import RAM_Storage
from cls.MotionDetector import MotionDetector
from cls.ActionManager import ActionManager
from cls.WatcherMemory import WatcherMemory

class CameraThread(Thread):
    """
    Camera Instance - It runs separate thread for recording in a loop and run additional separate thread for watcher loop
    """  

    def __init__(self, name, cnfg_daemon, cnfg_recorder, mqtt_client):
        """Init and assigning params before run"""
        Thread.__init__(self)
        self.logger = logging.getLogger(f"{name}:CameraThread")
        self.state_msg = 'stopped'
        self._stop_event = Event()
        self._recorder_started_event = Event()
#        self.recording = False
        self._watcher_started_event = Event()
        self.name = name
        self.cnfg_daemon = cnfg_daemon
        self.cnfg = cnfg_recorder
        self.mqtt_client = mqtt_client
        self.last_recorded_filename = '' # in this variable I will keep the latest recorded filename 
        self.last_snapshot = ''
        self.err_cnt = 0
        self.event_timeout = 5
        self.frame_width = None
        self.frame_height = None
        self.frame_dim = None
        self.watcher_thread = None
        self.proc_recorder = None

    
    def is_watching(self):
        return self._watcher_started_event.is_set()

    def is_recording(self):
        return self._recorder_started_event.is_set()

    def record_start(self):
        """ Start recording, if it is not started yet """
        self._recorder_started_event.set()
        self.logger.debug(f'receve "record_start" event')

    def record_stop(self):
        """ Stop recording gracefully"""
        if self._recorder_started_event.is_set():
            self._recorder_started_event.clear()
            if not self.proc_recorder is None:
                self.proc_recorder.send_signal(signal.SIGINT)
                #self.proc_recorder.kill()

        self.logger.debug(f'receve "record_stop" event')
        self.state_msg = 'stopped'
        self.mqtt_status()

    def stop(self, timeout=None):
        """ Stop the thread. """        
        self._stop_event.set()
        self.logger.debug(f'receve "stop" event')
        Thread.join(self, timeout)
    
    def mqtt_status(self):
        """ Sends MQTT status """
        payload = json.dumps({
                'name': self.name,
                'status': self.state_msg, 
                'error_cnt': self.err_cnt,
                'latest_file': '',#self.last_recorded_filename,
                'snapshot': self.last_snapshot
                })
        self.logger.debug(f'mqtt send "status" [{payload}]')
        self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),payload)

    def get_camera_info(self):
        """ Check if camera is available and calculate frame_shape"""
        if ping_ip(self.cnfg.ip):
            frame_shape = get_frame_shape(self.cnfg.stream_url())
            if not frame_shape is None:
                self.frame_width = frame_shape[1]
                self.frame_height = frame_shape[0]
                self.frame_dim = frame_shape[2]
        else:
            self.state_msg = 'inactive'
            self._recorder_started_event.clear()

    def run(self):
        """Main thread"""        
        if self.cnfg.record_autostart:
            self._recorder_started_event.set()
        self.get_camera_info()        
        while not self._stop_event.is_set(): 
            if self.state_msg in ('inactive'):
                self._stop_event.wait(self.cnfg.camera_ping_interval)
                self.get_camera_info()
            else:
                # watcher running in separate thread (start only once)
                if self.cnfg.is_motion_detection and self.watcher_thread is None:
                    self.watcher_thread = Thread(target=self.run_watcher_thread, args=()) 
                    self.watcher_thread.start()
                # recorder loop running in main thread
                self.run_recorder_loop()

    def run_recorder_loop(self):
        """ Function to run in a loop:
        1) ping if IP is active
        2) execute {cmd_recorder_start} to record file and take snapshots
        """
        i = 0 
        while not self._stop_event.is_set(): 
            if not self._recorder_started_event.is_set():
                i = 0
                self.logger.debug(f'Recording stopped. Sleeping..')
                self._recorder_started_event.wait(self.event_timeout)
            elif self.state_msg not in ('inactive'):               
                # run cmd_recorder_start
                cmd_recorder_start = self.cnfg.cmd_recorder_start() + f' -fh {self.frame_height} -fw {self.frame_width} -fd {self.frame_dim}'
                if cmd_recorder_start == '':
                    raise ValueError(f"Config value: 'cmd_recorder_start' is not defined")                    
                if (not self._stop_event.is_set()):
                    self.logger.debug(f'process run:> {cmd_recorder_start}')
                    self.proc_recorder = subprocess.Popen(cmd_recorder_start, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, universal_newlines=True)
                    self.state_msg = 'started'
                    self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),json.dumps({'status':self.state_msg }))
                    start_time = time.time()
                    try:
                        self.proc_recorder.wait(self.cnfg.record_time)
                    except subprocess.TimeoutExpired:
                        self.logger.debug(f'process.wait TimeoutExpired {self.cnfg.record_time}')
                    duration = time.time() - start_time
                    # detect if process run too fast (unsuccessful start)
                    if duration<self.cnfg.start_error_threshold:
                        self.err_cnt += 1
                        self.logger.debug(f"Probably can't start recording. Finished in {duration:.2f} sec (attempt {self.err_cnt})")
                        if (self.err_cnt % self.cnfg.start_error_atempt_cnt)==0:
                            self.logger.debug(f'Too many attempts to start with no success ({self.err_cnt}). Going to sleep for {self.cnfg.start_error_sleep} sec')
                            self.state_msg = 'error'
                            self.get_camera_info() # check if camera is available
                            self.mqtt_status()
                            self._stop_event.wait(self.cnfg.start_error_sleep)
                    else:
                        self.err_cnt = 0
                        self.logger.debug(f'process execution finished in {duration:.2f} sec')
                    self.proc_recorder = None
                    self.state_msg = 'restarting'
                    self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),json.dumps({'status':self.state_msg}))
                i += 1
                self.logger.debug(f'Running thread, iteration #{i}')
            elif self.state_msg in ('inactive'):
                break

    def watcher_start(self):
        """ Start recording, if it is not started yet """
        self._watcher_started_event.set()
        self.logger.debug(f'receve "watcher_start" event')

    def watcher_stop(self):
        """ Stop recording, if it is not started yet """
        self._watcher_started_event.clear()
        self.logger.debug(f'receve "watcher_stop" event')

    def run_watcher_thread(self):
        """
        1) Monitor provided RAM folder for newly taken frames
        2) Detect Motion between taken frames
        3) Run object detection if motion detected
        4) Remember for some time all detected object
        5) Take an action on frame where object was detected (email, copy, etc..)
        """
        # Mount RAM storage disk
        ram_storage = RAM_Storage(self.cnfg_daemon, logger_name = self.name)

        # Create storage manager
        storage = StorageManager(self.cnfg.storage_path(), self.cnfg.storage_max_size, logger_name = self.name)

        # Create MotionDetector
        motion_detector = MotionDetector(self.cnfg, logger_name = self.name)

        # Create ActionManager to run actions on files with detected objects
        action_manager = ActionManager(self.cnfg, name = self.name)

        # Remember detected objects, to avvoid triggering duplicate acctions
        watcher_memory = WatcherMemory(self.cnfg, name = self.name)

        cnt_no_object = 0 # count motion frames without objects for throttling
        def thread_process(filename): 
            """ Processing of each snapshot file must be done in separate thread
            """
            global cnt_no_object
            try:
                filename_wch = f"{filename[:-4]}.wch"
                try:
                    os.rename(filename, filename_wch)
                except FileNotFoundError:
                    return
                filename = filename[:-4]
                is_motion = motion_detector.detect(filename_wch)
                if self.cnfg_daemon.is_object_detection:
                    if not is_motion:
                        os.remove(filename_wch)
                    else:
                        filename_obj_wait = f"{filename}.obj.wait"
                        filename_obj_none = f"{filename}.obj.none"
                        filename_obj_found = f"{filename}.obj.found"
                        os.rename(filename_wch, filename_obj_wait)
                        # wait for file where object detection is complete
                        time_start = time.time()
                        while time.time()-time_start < self.cnfg_daemon.object_detector_timeout:                
                            if os.path.isfile(filename_obj_none):
                                cnt_no_object += 1
                                os.remove(filename_obj_none)
                                break
                            if os.path.isfile(filename_obj_found):
                                cnt_no_object = 0            
                                try: # Read info file
                                    with open(filename_obj_found+'.info') as f:
                                        info = json.loads(f.read())
                                        info['filename'] = filename_obj_found
                                except:
                                    self.logger.exception('Can''t load info file')
                                if watcher_memory.add(info):
                                    # Take actions on image where objects was found
                                    action_manager.run(filename_obj_found, info) 
                                # Remove temporary files
                                try:
                                    os.remove(filename_obj_found)
                                    os.remove(filename_obj_found+'.info')
                                except:
                                    self.logger.exception('Can''t delete temporary files')
                                break
                            time.sleep(self.cnfg.object_watch_delay)
                        if time.time()-time_start >= self.cnfg_daemon.object_detector_timeout:
                            self.logger.warning(f'Timeout: {filename} {time.time()-time_start} >= {self.cnfg_daemon.object_detector_timeout}')
                            # remove temporary file on timeout
                            for ext in ['.wch','.obj.wait','.obj.none','.obj.found','.obj.found.info']:
                                if os.path.isfile(filename+ext):
                                    os.remove(filename+ext)
                else: # in case if object detection is dissabled
                    # TODO: notify recorder that object detected
                    os.remove(filename_wch)
            except:
                self.logger.exception(f'Watch: {filename} failed')

        i = 0
        while not self._stop_event.is_set():
            if not self._watcher_started_event.is_set():
                self._watcher_started_event.wait(self.event_timeout)
            else:
                try:
                    i += 1
                    filename = storage.get_first_file(f"{ram_storage.storage_path}/{self.name}_*.rec")
                    if filename is None:
                        sleep_time = 1
                        self.logger.debug(f'Wait for "{self.name}_*.rec" file. Sleep {sleep_time} sec')
                        time.sleep(sleep_time)
                        continue
                    if os.path.isfile(filename):
                        throttling = math.ceil(cnt_no_object / self.cnfg.object_throttling)
                        if throttling>0:
                            if i % throttling != 0:
                                self.logger.debug(f'ObjectDetector throttling')
                                os.remove(filename)
                        thread = Thread(target=thread_process, args=(filename,))
                        thread.start()
                except:
                    self.logger.exception(f"watcher '{self.name}'")

def camera_create(name, cnfg_daemon, cnfg_recorder, mqtt_client):
    camera = CameraThread(name, cnfg_daemon, cnfg_recorder, mqtt_client)
    camera.start()
    return camera
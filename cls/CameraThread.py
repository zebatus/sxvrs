#!/usr/bin/env python

""" Camera Instance
It runs separate thread for recording in a loop and run additional separate thread for watcher loop
"""
import os
import sys
import logging
import json
from datetime import datetime
import time
from threading import Thread, Event
from queue import Queue, Empty
import subprocess
from operator import itemgetter
import math
import signal
import shlex
import re
import glob

from cls.misc import get_frame_shape, ping_ip, AnyChangeEvent
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
        self._watcher_started_event = Event() 
        self.name = name
        self.cnfg_daemon = cnfg_daemon
        self.cnfg = cnfg_recorder
        self.mqtt_client = mqtt_client
        self.latest_recorded_filename = '' # in this variable I will keep the latest recorded filename 
        self.latest_snapshot = ''
        self.err_cnt = 0
        self.event_timeout = 50
        self.frame_width = None
        self.frame_height = None
        self.frame_channels = None
        self.watcher_thread = None
        self.proc_recorder = None
        self.motion_throttling = ''
        self.cnt_motion_frame = 0
        self.cnt_obj_frame = 0
        self.cnt_in_memory = 0
        self.cnt_no_object = 0
        self.cnt_frame_analyzed = 0
        if self.cnfg.is_motion_detection:
            self._watcher_started_event.set()
        if self.cnfg.record_autostart:
            self._recorder_started_event.set()

    def record_start(self):
        """ Start recording, if it is not started yet """
        self.logger.debug(f'receve "record_start" event')
        self._recorder_started_event.set()
        self.mqtt_status()

    def record_stop(self):
        """ Stop recording gracefully"""
        self.logger.debug(f'receve "record_stop" event')
        if self._recorder_started_event.is_set():
            self._recorder_started_event.clear()            
            if not self.proc_recorder is None:
                self.proc_recorder.send_signal(signal.SIGINT)
                #self.proc_recorder.kill()
        self.mqtt_status()
        

    def watcher_start(self):
        """ Start watching, if it is not started yet """
        self.logger.debug(f'receve "watcher_start" event')
        self._watcher_started_event.set()
        self.mqtt_status()
        self.recorder_send_watch_state(self._watcher_started_event.is_set())

    def watcher_stop(self):
        """ Stop watching"""
        self.logger.debug(f'receve "watcher_stop" event')
        if self._watcher_started_event.is_set():
            self._watcher_started_event.clear()            
            self.recorder_send_watch_state(self._watcher_started_event.is_set())
            if not self._recorder_started_event.is_set() and not self._watcher_started_event.is_set() and not self.proc_recorder is None:
                self.proc_recorder.send_signal(signal.SIGINT)
                #self.proc_recorder.kill()
        self.mqtt_status()

    def stop(self, timeout=None):
        """ Stop the thread. """      
        try:  
            self._stop_event.set()
            if not self.proc_recorder is None and self.proc_recorder.returncode is None:
                self.proc_recorder.send_signal(signal.SIGINT)
            self.logger.debug(f'receve "stop" event')
            Thread.join(self, timeout)
        except:
            self.logger.exception(f"Can't stop thread: {self.name} ")
    
    def set_recorder_state(self, state):
        if self.state_msg != state:
            self.state_msg = state
            self.mqtt_status()

    def mqtt_status(self):
        """ Sends MQTT status """
        payload = json.dumps({
                'name': self.name,
                'status': self.state_msg, 
                'error_cnt': self.err_cnt,
                'latest_file': self.latest_recorded_filename,
                'snapshot': self.latest_snapshot,
                'record': self._recorder_started_event.is_set(),
                'watcher': self._watcher_started_event.is_set(),
                'motion throttling': self.motion_throttling,
                'cnt_frame_analyzed': self.cnt_frame_analyzed,
                'cnt_motion_frame': self.cnt_motion_frame,
                'object throttling': math.ceil(self.cnt_no_object / self.cnfg.object_throttling),
                'cnt_obj_frame': self.cnt_obj_frame,
                'cnt_in_memory': self.cnt_in_memory,
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
                self.frame_channels = frame_shape[2]
        else:
            self.set_recorder_state('inactive')
            self._recorder_started_event.clear()
            self._watcher_started_event.clear()

    def run(self):
        """Main thread"""        
        self.get_camera_info()        
        self.notify_status_thread = Thread(target=self.run_notify_status_loop, args=())
        self.notify_status_thread.start()
        while not self._stop_event.is_set(): 
            if self.state_msg in ('inactive'):
                if AnyChangeEvent(
                            self._recorder_started_event, 
                            self._watcher_started_event, 
                            self._stop_event
                        ).wait(self.cnfg.camera_ping_interval):
                    self.mqtt_status()
                self.get_camera_info()
            elif not (self._recorder_started_event.is_set() or self._watcher_started_event.is_set()):
                if AnyChangeEvent(
                            self._recorder_started_event, 
                            self._watcher_started_event, 
                            self._stop_event
                        ).wait(self.cnfg.camera_ping_interval):
                    self.mqtt_status()
            else:
                # watcher running in separate thread (start only once)
                if self.watcher_thread is None:
                    self.watcher_thread = Thread(target=self.run_watcher_thread, args=()) 
                    self.watcher_thread.start()
                # recorder loop running in main thread
                self.run_recorder_loop()

    def run_recorder_loop(self):
        """ Function to run in a loop:
        - execute {cmd_recorder_start} for start recording into file and take snapshots
        - parse execution output to get required variable values
        """
        i = 0 
        while not self._stop_event.is_set() and (self._recorder_started_event.is_set() or self._watcher_started_event.is_set()): 
            if self.state_msg in ('inactive'): # camera is not alive, then just exit from recording loop and wait in upper loop
                break               
            elif self._recorder_started_event.is_set(): # start recording                               
                # run cmd_recorder_start
                cmd_recorder_start = self.cnfg.cmd_recorder_start(
                    frame_height = self.frame_height,
                    frame_width = self.frame_width,
                    frame_channels = self.frame_channels
                )
                if cmd_recorder_start == '':
                    raise ValueError(f"Config value: 'cmd_recorder_start' is not defined")                    
                if (not self._stop_event.is_set()):
                    self.logger.debug(f'record process run:> {cmd_recorder_start}')
                    #self.proc_recorder = subprocess.Popen(cmd_recorder_start, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, universal_newlines=True)
                    self.proc_recorder = subprocess.Popen(shlex.split(cmd_recorder_start), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
                    self.set_recorder_state('started')
                    # need to parse sxvrs_recorder execution output, to catch required variables 
                    duration = self.parse_subprocess_output()                                        
                    # detect if process run too fast (unsuccessful start)
                    if duration<self.cnfg.start_error_threshold:
                        self.err_cnt += 1
                        self.logger.debug(f"Probably can't start recording. Finished in {duration:.2f} sec (attempt {self.err_cnt})")
                        if (self.err_cnt % self.cnfg.start_error_atempt_cnt)==0:
                            self.logger.debug(f'Too many attempts to start with no success ({self.err_cnt}). Going to sleep for {self.cnfg.start_error_sleep} sec')
                            self.get_camera_info() # check if camera is available
                            self.set_recorder_state('error')
                            AnyChangeEvent(
                                self._recorder_started_event, 
                                self._watcher_started_event, 
                                self._stop_event
                            ).wait(self.cnfg.start_error_sleep)
                    else:
                        self.err_cnt = 0
                        self.logger.debug(f'process execution finished in {duration:.2f} sec')
                    if self._recorder_started_event.is_set():
                        self.set_recorder_state('restarting')
                    else:
                        self.set_recorder_state('stopped')
                i += 1
                self.logger.debug(f'Running thread, iteration #{i}')
            elif self._watcher_started_event.is_set(): # take snapshots only (no recording)
                if self.proc_recorder is None or not self.proc_recorder.returncode is None:
                    cmd_take_snapshot = self.cnfg.cmd_take_snapshot(
                        frame_height = self.frame_height,
                        frame_width = self.frame_width,
                        frame_channels = self.frame_channels
                    )
                    self.logger.debug(f'snapshot process run:> {cmd_take_snapshot}')
                    self.proc_recorder = subprocess.Popen(shlex.split(cmd_take_snapshot), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
                    self.parse_subprocess_output(from_recorder=False)
                self.logger.debug(f'Recording is not started. Sleeping..')

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

        self.cnt_no_object = 0 # count motion frames without objects for throttling
        def thread_process(filename): 
            """ Processing of each snapshot file must be done in separate thread
            """
            try:
                self.cnt_frame_analyzed += 1
                filename_wch = f"{filename[:-4]}.wch"
                try:
                    os.rename(filename, filename_wch)
                except FileNotFoundError:
                    return
                filename = filename[:-4]
                label = filename[filename.rindex('_')+1:]
                is_motion = motion_detector.detect(filename_wch)
                if self.cnfg_daemon.is_object_detection:
                    if not is_motion:
                        os.remove(filename_wch)
                    else:
                        self.cnt_motion_frame += 1
                        if self.latest_recorded_filename != '' and self._recorder_started_event.is_set():
                            self.log_to_file(self.latest_recorded_filename+".motion.log", '', label)                        
                        filename_obj_wait = f"{filename}.obj.wait"
                        filename_obj_none = f"{filename}.obj.none"
                        filename_obj_found = f"{filename}.obj.found"
                        os.rename(filename_wch, filename_obj_wait)
                        # wait for file where object detection is complete
                        time_start = time.time()
                        while time.time()-time_start < self.cnfg_daemon.object_detector_timeout:                                     
                            if os.path.isfile(filename_obj_none):
                                self.cnt_no_object += 1
                                os.remove(filename_obj_none)
                                break
                            if os.path.isfile(filename_obj_found):
                                self.logger.debug(f'Detection finished: {filename_obj_found}')                                            
                                try: # Read info file
                                    with open(filename_obj_found+'.info') as f:
                                        info = json.loads(f.read())
                                        info['filename'] = filename_obj_found
                                except:
                                    self.logger.exception(f"Can't load info file: {filename_obj_found}.info")
                                    info = {"result": "can't load info file"}
                                    continue
                                if self.latest_recorded_filename != '' and self._recorder_started_event.is_set():
                                    self.log_to_file(self.latest_recorded_filename+".object.log", info, label)
                                self.cnt_obj_frame += 1
                                if watcher_memory.add(info):
                                    self.cnt_no_object = 0 # dissable object detection throttling
                                    # Take actions on image where objects was found
                                    action_manager.run(filename_obj_found, info) 
                                else:
                                    self.cnt_in_memory += 1
                                # Remove all temporary files
                                for file in glob.glob(filename_obj_found[:-10] + "*"):
                                    try:
                                        os.remove(file)
                                    except:
                                        self.logger.exception(f'Can''t delete temporary file: {file}')
                                break
                            time.sleep(self.cnfg.object_watch_delay)                 
                        if time.time()-time_start >= self.cnfg_daemon.object_detector_timeout:
                            self.logger.warning(f'Timeout: {filename} {time.time()-time_start:.2f} >= {self.cnfg_daemon.object_detector_timeout} sec')
                            # increase object throttling
                            self.cnt_no_object += 1
                            # remove temporary file on timeout
                            for ext in ['.wch','.obj.wait','.obj.none','.obj.found','.obj.found.info']:
                                if os.path.isfile(filename+ext):
                                    self.logger.warning(f"remove unprocessed file '{filename+ext}'' due timeout ({self.cnt_no_object})")
                                    os.remove(filename+ext)
                else: # in case if object detection is dissabled
                    # TODO: notify recorder that object detected
                    os.remove(filename_wch)
                #self.mqtt_status()
            except:
                self.logger.exception(f'Watch: {filename} failed')
        sleep_time = self.cnfg.motion_detection_sleep_time
        i = 0
        while not self._stop_event.is_set():
            if not self._watcher_started_event.is_set():
                self.logger.debug(f'Watcher {self.name}: wait for start {self.event_timeout} sec')
                if AnyChangeEvent(
                            self._recorder_started_event, 
                            self._watcher_started_event, 
                            self._stop_event
                        ).wait(self.event_timeout):
                    self.mqtt_status()
            else:
                try:
                    i += 1
                    for filename in storage.get_file_list(f"{ram_storage.storage_path}/{self.name}_*.rec"):
                        if filename is None:                        
                            #self.logger.debug(f'Wait for "{self.name}_*.rec" file. Sleep {sleep_time} sec')
                            time.sleep(sleep_time)
                            continue
                        if os.path.isfile(filename):
                            throttling = round(self.cnt_no_object / self.cnfg.object_throttling)
                            if throttling>0 and i % throttling != 0:
                                self.logger.debug(f'ObjectDetector throttling')
                                try:
                                    os.remove(filename)
                                except FileNotFoundError:
                                    pass # some times thread is not fast enoght to rename file first                                
                            else:
                                thread = Thread(target=thread_process, args=(filename,))
                                thread.start()

                except:
                    self.logger.exception(f"watcher failed '{self.name}'")

    def run_notify_status_loop(self):
        """ Send mqtt notify messages with given <send_status_interval> from separate thread
        """
        while not self._stop_event.is_set():            
            if not self._stop_event.wait(self.cnfg.send_status_interval):
                self.mqtt_status()
                self.cnt_obj_frame = 0
                self.cnt_in_memory = 0
                self.cnt_motion_frame = 0
                self.cnt_frame_analyzed = 0            

    def recorder_send_watch_state(self, state):
        """ interact with child process to set watcher state by keypress event
        w - to start watching
        e - to stop watching
        """
        if not self.proc_recorder is None:
            if state:
                self.proc_recorder.stdin.write(b'w') #_watcher_started_event.set()
            else:
                self.proc_recorder.stdin.write(b'e') #_watcher_started_event.clear()
            self.proc_recorder.stdin.flush()

    def parse_subprocess_output(self, from_recorder = True):
        self.mqtt_status()
        start_time = time.time()
        self.cnt_obj_frame = 0
        self.cnt_motion_frame = 0
        # interact with child process to set watcher state
        self.recorder_send_watch_state(self._watcher_started_event.is_set())
        # regex paterns to catch output
        pattern_videofile = re.compile(r".*Start record filename: \<(.*)\>.*")
        pattern_snapshotfile = re.compile(r".*Snapshot filename: \<(.*)\>.*")
        pattern_motion_throttling = re.compile(r".* frame throttling \((.*)\) for recorder.*")
        def parse_output(output, pattern, var):
            found = re.search(pattern, output)
            if not found is None:
                var = found.groups()[0]
            return var
        # non-blocking way to read from stdout of subprocess
        def enqueue_output(out, queue):
            for line in iter(out.readline, b''):
                queue.put(line)
            out.close()      
        q = Queue()
        t = Thread(target=enqueue_output, args=(self.proc_recorder.stdout, q))
        t.daemon = True # thread dies with the program
        t.start()                  
        duration = 0
        while ((not self._stop_event.is_set()) and ((from_recorder and self._recorder_started_event.is_set()) or (not from_recorder and self._watcher_started_event.is_set()) )) and duration < self.cnfg.record_time+5:
            #output = self.proc_recorder.stdout.readline()
            # read line without blocking
            try:  output = q.get_nowait() # or q.get(timeout=.1)
            except Empty:
                #print('no output yet')
                time.sleep(1)
                pass
            else: # got line
                # ... do something with line
                if output == b'' and self.proc_recorder.poll() is not None:
                    break
                if output:
                    output = output.decode("utf-8") 
                    self.logger.debug(output.strip()) # log output. maybe need to dissable this
                    self.latest_recorded_filename = parse_output(output, pattern_videofile, self.latest_recorded_filename)
                    self.latest_snapshot = parse_output(output, pattern_snapshotfile, self.latest_snapshot)
                    self.motion_throttling = parse_output(output, pattern_motion_throttling, self.motion_throttling)                
            duration = time.time() - start_time 
        # if process still running, then send stop signal
        if self.proc_recorder.returncode is None: 
            self.proc_recorder.send_signal(signal.SIGINT)
        self.proc_recorder = None  
        return duration     

    def log_to_file(self, filename, data, label=''):
        """ Function to write data into file """
        if isinstance(data, dict):
            data = json.dumps(data)
        with open(filename, "a") as f:
            f.write(f'{label}\t{data}\n')


def camera_create(name, cnfg_daemon, cnfg_recorder, mqtt_client):
    camera = CameraThread(name, cnfg_daemon, cnfg_recorder, mqtt_client)
    camera.start()
    return camera
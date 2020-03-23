#!/usr/bin/env python

""" Video Recording Thread
The recording is started in separate thread
"""
import os
import logging
import json
from datetime import datetime
import time
from threading import Thread, Event
import subprocess
from operator import itemgetter

from cls.misc import get_frame_shape

class vr_thread(Thread):
    """
    Each Video Recording Instanse must be run in separate thread
    """  

    def __init__(self, name, cnfg, mqtt_client):
        """Init and assigning params before run"""
        Thread.__init__(self)
        self.logger = logging.getLogger(f"Thread:{name}")
        self.state_msg = 'stopped'
        self._stop_event = Event()
        self._record_start_event = Event()
        self._record_stop_event = Event()
        self.recording = False
        self.name = name
        self.cnfg = cnfg
        self.mqtt_client = mqtt_client
        self.last_recorded_filename = '' # in this variable I will keep the latest recorded filename (for using for snapshots)
        self.last_snapshot = ''
        self.err_cnt = 0
   
    def record_start(self):
        """ Start recording, if it is not started yet """
        self._record_start_event.set()
        self.logger.debug(f'[{self.name}] receve "record_start" event')

    def record_stop(self):
        """ Stop recording, if it is not started yet """
        self._record_stop_event.set()
        self.logger.debug(f'[{self.name}] receve "record_stop" event')
        self.state_msg = 'stopped'
        self.mqtt_status()

    def stop(self, timeout=None):
        """ Stop the thread. """        
        self._stop_event.set()
        self.logger.debug(f'[{self.name}] receve "stop" event')
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
        self.logger.debug(f'[{self.name}] mqtt send "status" [{payload}]')
        self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),payload)

    def run(self):
        """Starting main thread loop"""
        # calculate frame_shape
        if self.cnfg.record_autostart:
            frame_shape = get_frame_shape(self.cnfg.stream_url())
            frame_height = frame_shape[0]
            frame_width = frame_shape[1]
            frame_dim = frame_shape[2]
        i = 0 
        while not self._stop_event.isSet():     
            if self.cnfg.record_autostart or self._record_start_event.isSet():
                self.recording = True
                self._record_start_event.clear()
            if self._record_stop_event.isSet():
                self.recording = False
                self._record_stop_event.clear()
            if self.recording:
                # run cmd_recorder_start
                cmd_recorder_start = self.cnfg.cmd_recorder_start() + f' -fh {frame_height} -fw {frame_width} -fd {frame_dim}'
                if cmd_recorder_start == '':
                    raise ValueError(f"Config value: 'cmd_recorder_start' is not defined")                    
                if (not self._stop_event.isSet()):
                    process = process = subprocess.Popen(cmd_recorder_start, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, universal_newlines=True)
                    self.state_msg = 'started'
                    self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),json.dumps({'status':self.state_msg }))
                    start_time = time.time()
                    try:
                        process.wait(self.cnfg.record_time)
                    except subprocess.TimeoutExpired:
                        self.logger.debug(f'[{self.name}] process.wait TimeoutExpired {self.cnfg.record_time}')
                    duration = time.time() - start_time
                    # detect if process run too fast (unsuccessful start)
                    if duration<self.cnfg.start_error_threshold:
                        self.err_cnt += 1
                        self.logger.debug(f"[{self.name}] Probably can't start recording. Finished in {duration:.2f} sec (attempt {self.err_cnt})")
                        if (self.err_cnt % self.cnfg.start_error_atempt_cnt)==0:
                            self.logger.debug(f'[{self.name}] Too many attempts to start with no success ({self.err_cnt}). Going to sleep for {self.cnfg.start_error_sleep} sec')
                            self.state_msg = 'error'
                            self.mqtt_status()
                            self._stop_event.wait(self.cnfg.start_error_sleep)
                    else:
                        self.err_cnt = 0
                        self.logger.debug(f'[{self.name}] process execution finished in {duration:.2f} sec')
                    self.state_msg = 'restarting'
                    self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),json.dumps({'status':self.state_msg}))
                i += 1
                self.logger.debug(f'[{self.name}] Running thread, iteration #{i}')
            else:
                i = 0
                self.logger.debug(f'[{self.name}] Sleeping thread')
                self._stop_event.wait(3)

def vr_create(name, cnfg, mqtt_client):
    vr = vr_thread(name, cnfg, mqtt_client)
    vr.start()
    return vr
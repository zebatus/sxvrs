#!/usr/bin/env python

""" Video Recording Instanse
The instanse is running in separate thread
"""
import os
import logging
import json
from datetime import datetime
from threading import Thread, Event
import queue, subprocess, signal

class vr_thread(Thread):
    """
    Each Video Recording Instanse must be run in separate thread
    """  
    def read_config(self, param):  
        """Function read configuration param from YAML returning local or global value"""
        if param in self.cnfg['sources'][self.name]:
            return self.cnfg['sources'][self.name][param]
        else:
            return self.cnfg['global'][param]

    def __init__(self, name, cnfg, mqtt_client):
        """Init and assigning params before run"""
        Thread.__init__(self)
        self._stop_event = Event()
        self._record_start_event = Event()
        self._record_stop_event = Event()
        self.recording = False
        self.name = name
        self.cnfg = cnfg
        self.mqtt_client = mqtt_client
        self.ip = self.read_config('ip')
        self.stream_url = self.read_config('stream_url')
        self.record_autostart = self.read_config('record_autostart')
        self.record_time = self.read_config('record_time')
        self.storage_max_size = self.read_config('storage_max_size')
        self.storage_path = self.read_config('storage_path')
        self.filename = self.read_config('filename')
        self.cmd_before = self.read_config('cmd_before')
        self.cmd = self.read_config('cmd')
        self.cmd_after = self.read_config('cmd_after')
    
    def record_start(self):
        """ Start recording, if it is not started yet """
        self._record_start_event.set()
        logging.debug(f'  receve "record_start" event for thread {self.name}')

    def record_stop(self):
        """ Stop recording, if it is not started yet """
        self._record_stop_event.set()
        logging.debug(f'  receve "record_stop" event for thread {self.name}')

    def stop(self, timeout=None):
        """ Stop the thread. """        
        self._stop_event.set()
        logging.debug(f'  receve "stop" event for thread {self.name}')
        Thread.join(self, timeout)

    def shell_execute(self, cmd, path):
        filename = self.filename.format(storage_path=path, name=self.name, datetime=datetime.now())
        stream_url = self.stream_url.format(ip=self.ip)
        cmd = cmd.format(filename=filename, ip=self.ip, stream_url=stream_url, record_time=self.record_time)
        logging.debug(f'shell_execute: {cmd}')
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, universal_newlines=True)
        return process

    def run(self):
        """Starting thread loop"""
        self.mqtt_client.subscribe(self.cnfg['mqtt']['topic'].format(name=self.name))  
        i = 0 
        while not self._stop_event.isSet():     
            if self.record_autostart or self._record_start_event.isSet():
                self.recording = True
            if self._record_stop_event.isSet():
                self.recording = False
            if self.recording:
                # Force create path
                path = self.storage_path.format(name=self.name, datetime=datetime.now())
                if not os.path.exists(path):
                    logging.debug(f'  path not existing: {path} \n try to create it..')
                    try:
                        os.makedirs(path)
                    except:
                        logging.exception(f'Can''t create path {path}')
                # force cleanup {path} by {storage_max_size}
                # take snapshot
                #self.mqtt_client.publish(self.cnfg['mqtt']['topic'].format(name=self.name),json.dumps({'status':'snapshot'}))
                # run cmd before start
                if self.cmd_before!=None and self.cmd_before!='':
                    process = self.shell_execute(self.cmd_before, path)
                # run cmd
                if self.cmd!=None and self.cmd!='':
                    process = self.shell_execute(self.cmd, path)
                    self.mqtt_client.publish(self.cnfg['mqtt']['topic'].format(name=self.name),json.dumps({'status':'started'}))
                    try:
                        process.wait(self.record_time)
                    except subprocess.TimeoutExpired:
                        logging.debug(f'/t {self.name}: process.wait TimeoutExpired {self.record_time}')
                    logging.debug(f'/t process execution finished')
                    self.mqtt_client.publish(self.cnfg['mqtt']['topic'].format(name=self.name),json.dumps({'status':'restarting'}))
                # run cmd after finishing
                if self.cmd_after!=None and self.cmd_after!='':
                    process = self.shell_execute(self.cmd_after, path)
            i += 1
            logging.debug(f'Running thread {self.name} iteration #{i}')
            self._stop_event.wait(1)


def vr_create(name, cnfg, mqtt_client):
    vr = vr_thread(name, cnfg, mqtt_client)
    vr.start()
    return vr
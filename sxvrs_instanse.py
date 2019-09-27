#!/usr/bin/env python

""" Video Recording Instanse
The instanse is running in separate thread
"""
import os
import logging
import json
from datetime import datetime
from threading import Thread

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
        self.name = name
        self.cnfg = cnfg
        self.mqtt_client = mqtt_client
        self.ip = self.read_config('ip')
        self.record_autostart = self.read_config('record_autostart')
        self.record_time = self.read_config('record_time')
        self.storage_max_size = self.read_config('storage_max_size')
        self.storage_path = self.read_config('storage_path')
        self.cmd_before = self.read_config('cmd_before')
        self.cmd = self.read_config('cmd')
        self.cmd_after = self.read_config('cmd_after')
    
    def run(self):
        """Starting thread"""
        self.mqtt_client.subscribe(self.cnfg['mqtt']['topic'].format(name=self.name))        
        if self.record_autostart:
            # Force create path
            path = self.storage_path.format(name=self.name, datetime=datetime.now())
            if not os.path.exists(path):
                logging.debug(f'  path not existing: {path} \n try to create it..')
                try:
                    os.makedirs(path)
                except:
                    logging.exception(f'Can''t create path {path}')
            # force clear path
            # take snapshot
            #self.mqtt_client.publish(self.cnfg['mqtt']['topic'].format(name=self.name),json.dumps({'status':'snapshot'}))
            # run cmd before start
            # run cmd
            self.mqtt_client.publish(self.cnfg['mqtt']['topic'].format(name=self.name),json.dumps({'status':'started'}))
            # run cmd after finishing


def vr_create(name, cnfg, mqtt_client):
    vr = vr_thread(name, cnfg, mqtt_client)
    vr.start()
    return vr
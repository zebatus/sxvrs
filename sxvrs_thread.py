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
try:
    from os import scandir
except ImportError:
    from scandir import scandir  # use scandir PyPI module on Python < 3.5


class vr_thread(Thread):
    """
    Each Video Recording Instanse must be run in separate thread
    """  

    def __init__(self, name, cnfg, mqtt_client):
        """Init and assigning params before run"""
        Thread.__init__(self)
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
        logging.debug(f'[{self.name}] receve "record_start" event')

    def record_stop(self):
        """ Stop recording, if it is not started yet """
        self._record_stop_event.set()
        logging.debug(f'[{self.name}] receve "record_stop" event')
        self.state_msg = 'stopped'
        self.mqtt_status()

    def stop(self, timeout=None):
        """ Stop the thread. """        
        self._stop_event.set()
        logging.debug(f'[{self.name}] receve "stop" event')
        Thread.join(self, timeout)
    
    def mqtt_status(self):
        """ Sends MQTT status """
        payload = json.dumps({
                'name': self.name,
                'status': self.state_msg, 
                'error_cnt': self.err_cnt,
                'latest_file': self.last_recorded_filename,
                'snapshot': self.last_snapshot
                })
        logging.debug(f'[{self.name}] mqtt send "status" [{payload}]')
        self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),payload)

    def shell_execute(self, cmd, filename):
        stream_url = self.cnfg.stream_url.format(ip=self.cnfg.ip)
        cmd = cmd.format(filename=filename, ip=self.cnfg.ip, stream_url=stream_url, record_time=self.cnfg.record_time)
        logging.debug(f'[{self.name}] shell_execute: {cmd}')
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, universal_newlines=True)
        return process

    def run(self):
        """Starting main thread loop"""
        i = 0 
        while not self._stop_event.isSet():     
            if self.cnfg.record_autostart or self._record_start_event.isSet():
                self.recording = True
                self._record_start_event.clear()
            if self._record_stop_event.isSet():
                self.recording = False
                self._record_stop_event.clear()
            if self.recording:
                # force cleanup {path} by {storage_max_size}
                self.clear_storage(os.path.dirname(self.cnfg.storage_path.format(name=self.name, datetime=datetime.now())))
                # Force create path
                path = self.cnfg.storage_path.format(name=self.name, datetime=datetime.now())
                if not os.path.exists(path):
                    logging.debug(f'[{self.name}] path not existing: {path} \n try to create it..')
                    try:
                        os.makedirs(path)
                    except:
                        logging.exception(f'[{self.name}] Can''t create path {path}')
                filename_new = self.cnfg.filename.format(storage_path=path, name=self.name, datetime=datetime.now())                
                # take snapshot
                if self.cnfg.snapshot_filename != '' and self.cnfg.snapshot_cmd != '':
                    if '{last_recorded_filename}' in self.cnfg.snapshot_cmd:
                        snapshot_filename = self.cnfg.snapshot_filename.format(name=self.name)
                        logging.debug(f"[{self.name}] Take snapshot from File to file: {snapshot_filename}")
                        if self.last_recorded_filename=='' or not os.path.isfile(self.last_recorded_filename):
                            filename = self.cnfg.stream_url # if there was no any recordings yet, then take snapshot from URL stream
                        else:
                            filename = self.last_recorded_filename
                        process = self.shell_execute(self.cnfg.snapshot_cmd.format(
                                snapshot_filename = snapshot_filename,
                                last_recorded_filename = filename
                                ),
                                filename = ''
                            )
                        self.last_snapshot = snapshot_filename
                    else:                     
                        logging.debug(f"[{self.name}] Take snapshot from URL to file: {self.cnfg.snapshot_filename}")
                        process = self.shell_execute(self.cnfg.snapshot_cmd.format(
                                snapshot_filename=self.cnfg.snapshot_filename.format(name=self.name),
                                # additionally provide all possible variables for future use (TODO: it is better to rewrite this in more pythonic way)
                                filename="{filename}",
                                ip=self.cnfg.ip,
                                stream_url="{stream_url}",
                                record_time=self.cnfg.record_time,
                                storage_path=path,
                                name=self.name,
                                datetime=datetime.now()
                                ),
                                filename = ''
                            )
                    self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),json.dumps({'status':'snapshot'}))
                # run cmd before start
                if self.cnfg.cmd_before!=None and self.cnfg.cmd_before!='':
                    process = self.shell_execute(self.cnfg.cmd_before, filename_new)
                # run cmd
                if (not self._stop_event.isSet()) and self.cnfg.cmd!=None and self.cnfg.cmd!='':
                    process = self.shell_execute(self.cnfg.cmd, filename_new)
                    self.state_msg = 'started'
                    self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),json.dumps({'status':self.state_msg }))
                    start_time = time.time()
                    try:
                        process.wait(self.cnfg.record_time)
                    except subprocess.TimeoutExpired:
                        logging.debug(f'[{self.name}] process.wait TimeoutExpired {self.cnfg.record_time}')
                    duration = time.time() - start_time
                    # detect if process run too fast (unsuccessful start)
                    if duration<self.cnfg.start_error_threshold:
                        self.err_cnt += 1
                        logging.debug(f"[{self.name}] Probably can't start recording. Finished in {duration:.2f} sec (attempt {self.err_cnt})")
                        if (self.err_cnt % self.cnfg.start_error_atempt_cnt)==0:
                            logging.debug(f'[{self.name}] Too many attempts to start with no success ({self.err_cnt}). Going to sleep for {self.cnfg.start_error_sleep} sec')
                            self.state_msg = 'error'
                            self.mqtt_status()
                            self._stop_event.wait(self.cnfg.start_error_sleep)
                    else:
                        self.err_cnt = 0
                        logging.debug(f'[{self.name}] process execution finished in {duration:.2f} sec')
                    if not os.path.isfile(filename_new):
                        self.state_msg = 'error'
                    if self.state_msg != 'error':
                        self.last_recorded_filename = filename_new
                    self.state_msg = 'restarting'
                    self.mqtt_client.publish(self.cnfg.mqtt_topic_recorder_publish.format(source_name=self.name),json.dumps({'status':self.state_msg}))
                # run cmd after finishing
                if self.cnfg.cmd_after!=None and self.cnfg.cmd_after!='':
                    process = self.shell_execute(self.cnfg.cmd_after, path)
                i += 1
                logging.debug(f'[{self.name}] Running thread, iteration #{i}')
            else:
                i = 0
                logging.debug(f'[{self.name}] Sleeping thread')
                self._stop_event.wait(3)

    def clear_storage(self, cleanup_path):
        """function removes old files in Camera folder. This gives ability to write files in neverending loop, when old records are rewritedby new ones"""
        try:            
            max_size = self.storage_max_size*1024*1024*1024
            logging.debug(f"[{self.name}] Start storage cleanup on path: {cleanup_path} (Max size: {max_size/1024/1024/1024:.2f} GB)")
            self.file_list = []
            self.folder_size(cleanup_path)
            # sort list of files by datetime value (DESC)
            self.file_list = sorted(self.file_list, key=itemgetter('dt'), reverse=True)
            # calculate cumulative size
            i = 0
            cumsum = 0
            for item in self.file_list:
                cumsum += item['size']
                item['cumsum'] = cumsum
                if(cumsum > max_size):
                    i = i + 1               
                    logging.info(f"[{self.name}] Removing file {i}: {item['file']}")
                    os.remove(item['file'])
                    self.mqtt_client.publish(self.cnfg['mqtt']['topic_publish'].format(source_name=self.name)
                        , json.dumps({
                                        'status': self.state_msg,
                                        'deleted': item['file']
                                        })
                    )
            # remove empty directories
            for (_path, _dirs, _files) in os.walk(cleanup_path, topdown=False):
                if _files or _dirs: continue # skip remove
                try:
                    os.rmdir(_path)
                    logging.debug(f'[{self.name}] Remove empty folder: {_path}')
                except OSError:
                    logging.exception('[{self.name}] Folder not empty :')
        except:
            logging.exception(f"[{self.name}] Storage Cleanup Error")

    def folder_size(self, path='.'):
        total = 0
        for entry in scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
                row = {
                            'file': entry.path,
                            'size': entry.stat().st_size,
                            'dt': entry.stat().st_mtime, # have to use last modification time because of Linux: there is no easy way to get correct creation time value
                         }
                self.file_list.append(row)
            elif entry.is_dir(follow_symlinks=False):
                total += self.folder_size(entry.path)
        return total

def vr_create(name, cnfg, mqtt_client):
    vr = vr_thread(name, cnfg, mqtt_client)
    vr.start()
    return vr
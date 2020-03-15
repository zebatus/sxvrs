#!/usr/bin/env python

import yaml
import logging, logging.config
from datetime import datetime

class config_reader():
    """     The aim of this class to read config file
    - combine global and local recorder configs
    - set default values if there key is ommited in config file
    - can be used both in main daemon process and child recorders
    """
    def __init__(self, filename, name=None):
        """ Load configuration file.
        """
        try:
            with open(filename) as yaml_data_file:
                txt_data = yaml_data_file.read()     
                cnfg = yaml.load(txt_data, Loader=yaml.FullLoader)
        except:
            logging.exception('Exception in reading config from YAML')
            raise  
        self.data = cnfg
        # setup logger from yaml config file
        logging.config.dictConfig(cnfg['logger'])          
        if name is None:
            name = 'sxvrs_daemon'
        self.mqtt_name = cnfg['mqtt'].get('name', name)
        self.mqtt_server_host = cnfg['mqtt'].get('server_ip','127.0.0.1')
        self.mqtt_server_port = cnfg['mqtt'].get('server_port', 1883)
        self.mqtt_server_keepalive = cnfg['mqtt'].get('server_keepalive',60)
        self.mqtt_login = cnfg['mqtt'].get('login', None)
        self.mqtt_pwd = cnfg['mqtt'].get('pwd', None)
        self.mqtt_topic_daemon_publish = cnfg['mqtt'].get('topic_publish', 'sxvrs/clients/{source_name}')
        self.mqtt_topic_daemon_subscribe = cnfg['mqtt'].get('topic_subscribe', 'sxvrs/daemon/{source_name}')
        # set config for each recorder
        self.recorders = {}
        for recorder in cnfg['recorders']:
            self.recorders[recorder] = recorder_configuration(cnfg, recorder)

class recorder_configuration():
    """ Combines global and local parameter for given redcorder record
    """
    def combine(self, param, default=None):  
        """Function read configuration param from YAML returning local or global value"""
        if param in self.data['recorders'][self.name]:
            return self.data['recorders'][self.name][param]
        else:
            if param in self.data['global']:
                return self.data['global'][param]
            else:
                return default
    def __init__(self, cnfg, name):
        self.data = cnfg
        self.mqtt_topic_recorder_publish = cnfg['mqtt'].get('topic_publish', 'sxvrs/clients/{source_name}')
        self.mqtt_topic_recorder_subscribe = cnfg['mqtt'].get('topic_subscribe', 'sxvrs/daemon/{source_name}')
        # unique name for the recorder instance (used in mqtt and filename template)
        self.name = name 
        # ip adress for the camera (used in stream_url template)
        self.ip = self.combine('ip')
        # stream_url - ffmpeg will connect there (can be formated with {ip} param)
        self._stream_url = self.combine('stream_url')
        # start recording immidiately after creation on object
        self.record_autostart = self.combine('record_autostart', default=False)
        # the duration of the recording into one file
        self.record_time = self.combine('record_time', default=600)
        # maximum storage folder size in GB. If it exceeds, then the oldes files will be removed
        self.storage_max_size = self.combine('storage_max_size', default=10)
        # folder for storing recordings. This is template and can be formated with {name} and {datetime} params
        self._storage_path = self.combine('storage_path')
        # filename for recording. This is template and can be formated with {name} and {datetime} params
        self._filename = self.combine('filename', default="{storage_path}/{name}_{datetime:%Y%m%d_%H%M%S}.ts")
        # filename for the snapshot. This is template and can be formated with {name} and {datetime} params
        self._snapshot_filename = self.combine('snapshot_filename')
        # shell command for recorder start (used in daemon thread)
        self._cmd_recorder_start = self.combine('cmd_recorder_start')
        # shell command to start ffmpeg and read frames (used inside recorder subprocess)
        self._cmd_ffmpeg_read = self.combine('cmd_ffmpeg_read')
        # shell command to start ffmpeg and write video from collected frames (used inside recorder subprocess)
        self._cmd_ffmpeg_write = self.combine('cmd_ffmpeg_write')
        # if there is too many errors to connect to video source, then try to sleep some time before new attempts
        self.start_error_atempt_cnt = self.combine('start_error_atempt_cnt', default=10)
        self.start_error_threshold = self.combine('start_error_threshold', default=10)
        self.start_error_sleep = self.combine('start_error_sleep', default=600)
        # ffmpeg buffer frame count
        self.ffmpeg_buffer_frames = self.combine('ffmpeg_buffer_frames', default=16)

    def stream_url(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = self.name
        if 'ip' not in kwargs:
            kwargs['ip'] = self.ip
        return self._stream_url.format(**kwargs)

    def storage_path(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = self.name
        if 'datetime' not in kwargs:
            kwargs['datetime'] = datetime.now()
        return self._storage_path.format(**kwargs)
    
    def filename(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = self.name
        if 'datetime' not in kwargs:
            kwargs['datetime'] = datetime.now()
        if 'storage_path' not in kwargs:
            kwargs['storage_path'] = self.storage_path()
        return self._filename.format(**kwargs)
    
    def snapshot_filename(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = self.name
        if 'datetime' not in kwargs:
            kwargs['datetime'] = datetime.now()
        if 'storage_path' not in kwargs:
            kwargs['storage_path'] = self.storage_path()
        return self._snapshot_filename.format(**kwargs)
        
    def cmd_ffmpeg_read(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = self.name
        if 'datetime' not in kwargs:
            kwargs['datetime'] = datetime.now()
        if 'storage_path' not in kwargs:
            kwargs['storage_path'] = self.storage_path()
        if 'stream_url' not in kwargs:
            kwargs['stream_url'] = self.stream_url()
        return self._cmd_ffmpeg_read.format(**kwargs)
    
    def cmd_ffmpeg_write(self, **kwargs):
        if 'name' not in kwargs:
            kwargs['name'] = self.name
        if 'datetime' not in kwargs:
            kwargs['datetime'] = datetime.now()
        if 'storage_path' not in kwargs:
            kwargs['storage_path'] = self.storage_path()
        if 'filename' not in kwargs:
            kwargs['filename'] = self.filename()
        return self._cmd_ffmpeg_write.format(**kwargs)
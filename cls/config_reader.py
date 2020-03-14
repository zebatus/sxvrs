#!/usr/bin/env python

import yaml
import logging, logging.config

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
        self.stream_url = self.combine('stream_url')
        # start recording immidiately after creation on object
        self.record_autostart = self.combine('record_autostart', default=False)
        # the duration of the recording into one file
        self.record_time = self.combine('record_time', default=600)
        # maximum storage folder size in GB. If it exceeds, then the oldes files will be removed
        self.storage_max_size = self.combine('storage_max_size', default=10)
        # folder for storing recordings. This is template and can be formated with {name} and {datetime} params
        self.storage_path = self.combine('storage_path')
        # filename for recording. This is template and can be formated with {name} and {datetime} params
        self.filename = self.combine('filename', default="{storage_path}/{name}_{datetime:%Y%m%d_%H%M%S}.ts")
        # shell command to execute just before recording starts
        self.cmd_before = self.combine('cmd_before')
        # shell command for recording execution
        self.cmd = self.combine('cmd')
        # shell commnad to execute after recording is ended
        self.cmd_after = self.combine('cmd_after')
        # filename for the snapshot. This is template and can be formated with {name} and {datetime} params
        self.snapshot_filename = self.combine('snapshot_filename')
        # shell command to obtain snapshot for the last file
        self.snapshot_cmd = self.combine('snapshot_cmd')
        # if there is too many errors to connect to video source, then try to sleep some time before new attempts
        self.start_error_atempt_cnt = self.combine('start_error_atempt_cnt', default=10)
        self.start_error_threshold = self.combine('start_error_threshold', default=10)
        self.start_error_sleep = self.combine('start_error_sleep', default=600)        
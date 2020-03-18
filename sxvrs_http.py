#!/usr/bin/env python

"""     This is HTTPServer for showing snapshots 
Dependencies:
    pip install pyyaml paho-mqtt flask
    sudo apt install imagemagick 
"""

__author__      = "Rustem Sharipov"
__copyright__   = "Copyright 2019"
__license__     = "GPL"
__version__     = "0.2.0"
__maintainer__  = "Rustem Sharipov"
__email__       = "zebatus@gmail.com"
__status__      = "Development"


import os, sys, logging, logging.config
import yaml
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt
from sxvrs_recorder import vr_create
import html
import io
import socketserver
import urllib.parse
import mimetypes
import subprocess


from cls.config_reader import config_reader
from cls.HTTPServer import StartHTTPServer
from cls.misc import check_topic

# Global variables
recorders = []

# Get running script name
script_path, script_name = os.path.split(os.path.splitext(__file__)[0])
app_label = script_name + f'_{datetime.now():%H%M}'
stored_exception=None

logger = logging.getLogger(script_name)

# Load configuration files
cnfg = config_reader(
        os.path.join('cnfg' ,'sxvrs.yaml'), 
        name_http = 'sxvrs_http',
        log_filename = 'http'
    )

mqtt_name = cnfg.mqtt_name_http
mqtt_server_host = cnfg.mqtt_server_host
mqtt_server_port = cnfg.mqtt_server_port
mqtt_server_keepalive = cnfg.mqtt_server_keepalive
mqtt_login = cnfg.mqtt_login
mqtt_pwd = cnfg.mqtt_pwd
mqtt_topic_publish_tmpl = cnfg.mqtt_topic_client_publish
mqtt_topic_subscribe_tmpl = cnfg.mqtt_topic_client_subscribe

# Class for VR
class Recorder():
    def __init__(self, name):
        self.name = name
        self.status = 'None'
        self.error_cnt = 0 
        self.latest_file = ''
        self.snapshot = ''

def mqtt_publish_recorder(recorder, message):
    if isinstance(message, dict):
        message = json.dumps(message)
    mqtt_client.publish(mqtt_topic_publish_tmpl.format(source_name=recorder.name), message)
    logging.debug(f"MQTT publish: {mqtt_topic_publish_tmpl.format(source_name=recorder.name)} {message}")

# MQTT event listener
def on_mqtt_message(client, userdata, message):
    """Provides reaction on all events received from MQTT broker"""
    global vr_list, mqtt_topic_publish_tmpl
    try:
        if len(message.payload)>0:
            payload = json.loads(str(message.payload.decode("utf-8")))
            # topic = list
            if check_topic(message.topic, "list"):
                logger.debug(f"receive list: {payload}")
                vr_list = []
                for name in payload:
                    vr_list.append(Recorder(name))
                    mqtt_client.publish(mqtt_topic_publish_tmpl.format(source_name=name), json.dumps({'cmd':'status'}))
                    logger.debug(f"MQTT publish: {mqtt_topic_publish_tmpl.format(source_name=name)} {{'cmd':'status'}}")
            # topic = <recorder_name>
            else:
                for vr in vr_list:
                    if check_topic(message.topic, vr.name.lower()):
                        if 'status' in payload:
                            vr.status = payload['status']
                        if 'error_cnt' in payload:
                            vr.error_cnt = payload['error_cnt']
                        if 'latest_file' in payload:
                            vr.latest_file = payload['latest_file']
                        if 'snapshot' in payload:
                            vr.snapshot = payload['snapshot']
    except:
        logger.exception(f'Error on_mqtt_message() topic: {message.topic} msg_len={len(message.payload)}')

def on_mqtt_connect(client, userdata, flags, rc):
    client.connection_rc = rc
    if rc==0:
        client.is_connected = True
        logger.info(f"Connected to MQTT: {mqtt_server_host}:{mqtt_server_port} rc={str(rc)}")
        mqtt_client.subscribe(mqtt_topic_subscribe_tmpl.format(source_name='#'))  
        logger.debug(f"MQTT subscribe: {mqtt_topic_subscribe_tmpl.format(source_name='#')}")
        time.sleep(1)
        mqtt_client.publish(mqtt_topic_publish_tmpl.format(source_name='list'))
        logger.debug(f"MQTT publish: {mqtt_topic_publish_tmpl.format(source_name='list')}")
    else:
        logging.error(f"MQTT connection failure with code={rc}")

# setup MQTT connection
try:
    mqtt_client = mqtt.Client(mqtt_name) #create new instance
    mqtt_client.is_connected = False
    mqtt_client.connection_rc = 3
    mqtt_client.enable_logger(logger)
    mqtt_client.on_message=on_mqtt_message #attach function to callback
    mqtt_client.on_connect=on_mqtt_connect #attach function to callback
    #try to connect to broker in a loop, until server becomes available
    logger.debug(f"host={mqtt_server_host}, port={mqtt_server_port}, keepalive={mqtt_server_keepalive}")
    mqtt_client.loop_start() 
    if mqtt_login!=None: 
        mqtt_client.username_pw_set(mqtt_login, mqtt_pwd)
    while mqtt_client.connection_rc==3:
        try:
            logger.info(f"Try to connect to MQTT Server..")                
            mqtt_client.connect(mqtt_server_host, 
                port = mqtt_server_port,
                keepalive = mqtt_server_keepalive
                ) 
            while not mqtt_client.is_connected: # blocking code untill connection
                time.sleep(1)
        except ConnectionRefusedError:
            mqtt_client.connection_rc==3
            wait = 1
            logger.info(f"Server is offline. Wait {wait} sec before retry")
            time.sleep(wait) # if server is not available, then wait for it
except :
    logger.exception(f"Can't connect to MQTT broker at address: {mqtt_server_host}:{mqtt_server_port}")
    stored_exception=sys.exc_info()    


#########
from flask import Flask
flask_app = Flask(__name__)

def refresh_recorder_status(recorder=None):
    """This function is for running of refreshment of the status for all cam"""
    global recorders
    if recorder is None:
        for recorder in recorders:
            mqtt_publish_recorder(recorder, {'cmd':'status'})
    else:
        mqtt_publish_recorder(None, {'cmd':'status'})
        mqtt_client.publish(mqtt_topic_publish_tmpl.format(source_name='list'))
        logging.debug(f"MQTT publish: {mqtt_topic_publish_tmpl.format(source_name='list')}")


if stored_exception==None:
    # start HTTP Server
    logging.info(f"Starting HTTP Server on http://{cnfg.http_server_host}:{cnfg.http_server_port} Press [CTRL+C] to exit")
    is_started = False    
    while not is_started:
        try:
            flask_app.run(
                    host = cnfg.http_server_host, 
                    port = cnfg.http_server_host, 
                    debug = True
                )        
            is_started = True
        except OSError as e:
            if e.errno == 98:
                logging.error(f"Port {cnfg.http_server_host} already in use. Wait 5 sec and retry..")
                time.sleep(5)
            else:
                logging.exception("Can't start HTTP Server")
                sys.exit(1)
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
#!/usr/bin/env python

"""     Simple eXtendable Video Recording Script
Main features:
    1) The aim of this script is to run in a loop such tools like ffmpeg, vlc, openrtsp or any other command line application 
    2) Script able to maintain free space and record files in a loop
    3) Communicate with other software thrue MQTT

Dependencies:
    pip install pyyaml paho-mqtt
"""

__author__      = "Rustem Sharipov"
__copyright__   = "Copyright 2019"
__license__     = "GPL"
__version__     = "1.0.1"
__maintainer__  = "Rustem Sharipov"
__email__       = "zebatus@gmail.com"
__status__      = "Production"


import os, sys, logging, logging.config
import yaml
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt

from sxvrs_instanse import vr_create

# Get running script name
script_path, script_name = os.path.split(os.path.splitext(__file__)[0])
app_label = script_name + f'_{datetime.now():%H%M}'
stored_exception=None
vr_list = []

logger = logging.getLogger(script_name)

# Load configuration files
try:
    with open(os.path.join('cnfg' ,script_name + '.yaml')) as yaml_data_file:
        txt_data = yaml_data_file.read()     
        cnfg = yaml.load(txt_data, Loader=yaml.FullLoader)
except:
    logger.exception('Exception in reading config from YAML')
    raise

# setup logger from yaml config file
logging.config.dictConfig(cnfg['logger'])

# MQTT event listener
def on_mqtt_message(client, userdata, message):
    """Provides reaction on all events received from MQTT broker"""
    try:
        payload = ''
        if len(message.payload)>0:
            logger.debug("MQTT received " + str(message.payload.decode("utf-8")))
            logger.debug("MQTT topic=" + message.topic)
            logger.debug("MQTT qos=" + str(message.qos))
            logger.debug("MQTT retain flag=" + str(message.retain))
            payload = json.loads(str(message.payload.decode("utf-8")))
        for vr in vr_list:
            if message.topic.endswith("/"+vr.name) and 'cmd' in payload:
                if payload['cmd']=='start':
                    vr.record_start()
                elif payload['cmd']=='stop':
                    vr.record_stop()
                elif payload['cmd']=='status':
                    vr.mqtt_status()
        if message.topic.endswith("/list"):
            names = []
            for vr in vr_list:
                names.append(vr.name)
            mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name='list'),            
                        json.dumps(names))
            logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name='list')} [{names}]")
    except:
        logger.exception(f'Error on_mqtt_message() topic: {message.topic} msg_len={len(message.payload)}')

def on_mqtt_connect(client, userdata, flags, rc):
    client.connection_rc = rc
    if rc==0:
        client.is_connected = True

# setup MQTT connection
try:
    mqtt_client = mqtt.Client(cnfg['mqtt']['name']) #create new instance
    mqtt_client.is_connected = False
    mqtt_client.connection_rc = 3
    mqtt_client.enable_logger(logger)
    mqtt_client.on_message=on_mqtt_message #attach function to callback
    mqtt_client.on_connect=on_mqtt_connect #attach function to callback
    #try to connect to broker in a loop, until server becomes available
    logger.debug(f"host={cnfg['mqtt']['server_ip']}, port={cnfg['mqtt']['server_port']}, keepalive={cnfg['mqtt']['server_keepalive']}")
    mqtt_client.loop_start() 
    while mqtt_client.connection_rc==3:
        try:
            logger.info(f"Try to connect to MQTT Server..")                
            mqtt_client.connect(cnfg['mqtt']['server_ip'], 
                port=cnfg['mqtt']['server_port'],
                keepalive=cnfg['mqtt']['server_keepalive']
                ) 
            while not mqtt_client.is_connected: # blocking code untill connection
                time.sleep(1)
        except ConnectionRefusedError:
            mqtt_client.connection_rc==3
            wait = 1
            logger.info(f"Server is offline. Wait {wait} sec before retry")
            time.sleep(wait) # if server is not available, then wait for it
    logger.info(f"Connected to MQTT: {cnfg['mqtt']['server_ip']}")
    mqtt_client.subscribe(cnfg['mqtt']['topic_subscribe'].format(source_name='#'))  
    logger.debug(f"MQTT subscribe: {cnfg['mqtt']['topic_subscribe'].format(source_name='#')}")
except :
    logger.exception(f"Can't connect to MQTT broker at address: {cnfg['mqtt']['server_ip']}")
    stored_exception=sys.exc_info()    

if stored_exception==None:
    logger.info(f'! Script started: "{script_name}" Press [CTRL+C] to exit')
    # create and start all instances from config
    cnt_instanse = 0
    for instanse in cnfg['sources']:
        vr_list.append(vr_create(instanse, cnfg, mqtt_client))
        cnt_instanse += 1

    # Main loop start
    while True:
        try:
            print(f'\r{datetime.now()}: recording {cnt_instanse}     ', end = '\r')
            time.sleep(2)
            if stored_exception:
                break        
        except (KeyboardInterrupt, SystemExit):
            logger.info("[CTRL+C detected]")
            stored_exception=sys.exc_info()

    # Stop all instances
    for vr in vr_list:
        vr.stop()
        logger.debug(f"   stoping instance: {vr.name}")
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    logger.info('# Script terminated')

if stored_exception and stored_exception[0]!=KeyboardInterrupt:
    raise Exception(stored_exception[0], stored_exception[1], stored_exception[2])

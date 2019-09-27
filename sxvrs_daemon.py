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
    logger.debug("message received " + str(message.payload.decode("utf-8")))
    logger.debug("message topic=" + message.topic)
    logger.debug("message qos=" + str(message.qos))
    logger.debug("message retain flag=" + str(message.retain))
    #payload = json.loads(str(message.payload.decode("utf-8")))[0]
    for vr in vr_list:
        if message.topic.endswith("/"+vr.name):
            print('found !!')


# setup MQTT connection
try:
    mqtt_client = mqtt.Client(cnfg['mqtt']['name']) #create new instance
    mqtt_client.enable_logger(logger)
    mqtt_client.on_message=on_mqtt_message #attach function to callback
    mqtt_client.connect(cnfg['mqtt']['server_ip']) #connect to broker
    mqtt_client.loop_start() #start the loop
    logger.info(f"Connected to MQTT: {cnfg['mqtt']['server_ip']}")
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
    logger.info('# Script terminated')

if stored_exception and stored_exception[0]!=KeyboardInterrupt:
    raise Exception(stored_exception[0], stored_exception[1], stored_exception[2])

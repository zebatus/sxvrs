#!/usr/bin/env python

"""     Simple eXtendable Video Recording Script
Main features:
    1) The aim of this script is to run in a loop such tools like ffmpeg, vlc, openrtsp or any other command line application 
    2) Script able to maintain free space and record files in a loop
    3) Communicate with other software thrue MQTT

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
import time
from datetime import datetime


# Get running script name
script_path, script_name = os.path.split(os.path.splitext(__file__)[0])
app_name = script_name + f'_{datetime.now():%H%M}' # unique name for PGAdmin

logger = logging.getLogger(script_name)

# Load configuration files
try:
    with open(os.path.join('cnfg' ,script_name + '.yaml')) as yaml_data_file:
        txt_data = yaml_data_file.read()     
        cnfg = yaml.load(txt_data, Loader=yaml.FullLoader)
except:
    logger.exception('Exception in ConfigRead_YAML')
    raise

# setup logger
logging.config.dictConfig(cnfg['logger'])

# Main loop start
logger.info(f'! Script started: "{script_name}" Press [CTRL+C] to exit')
stored_exception=None
while True:
    try:
        if stored_exception:
            break        
    except KeyboardInterrupt:
        logger.info("[CTRL+C detected]")
        stored_exception=sys.exc_info()
    finally:
        print(f'\r{datetime.now()}: recording 0 from 0     ', end = '\r')
        time.sleep(.5)

logger.info('# Script terminated')
if stored_exception:
    raise Exception(stored_exception[0], stored_exception[1], stored_exception[2])
sys.exit()
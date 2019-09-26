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

def ConfigRead_YAML(filename):
    """
    Loading config values from a files.
    Returns YAML objects loaded from: <filename.yaml>
    """
    def read(filename):
        try:
            with open(filename) as yaml_data_file:
                txt_data = yaml_data_file.read()     
                yaml_data = yaml.load(txt_data, Loader=yaml.FullLoader)
        except:
            logger.exception('Exception in ConfigRead_YAML')
            raise
        return yaml_data
    cnfg = read(filename)
    return cnfg

def setup_logging(config, env_key='yamlLOG'):
    """
    Setup logging configuration
    """
    value = os.getenv(env_key, None)
    if value:
        path = value
        if os.path.exists(path):
            with open(path, 'rt') as f:
                config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)
    else:
        logging.config.dictConfig(config)

# Get running script name
script_path, script_name = os.path.split(os.path.splitext(__file__)[0])
app_name = script_name + f'_{datetime.now():%H%M}' # unique name for PGAdmin

# Load configuration files
cnfg = ConfigRead_YAML(os.path.join('config' ,script_name + '.yaml'))

# setup logger
setup_logging(script_name)
logger = logging.getLogger(script_name)

logger.info(f'! Script started: "{script_name}" ')
stored_exception=None

while True:
    try:
        if stored_exception:
            break
        time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[CTRL+C detected]")
        stored_exception=sys.exc_info()
    finally:
        logger.info('# Script terminated')

if stored_exception:
    raise Exception(stored_exception[0], stored_exception[1], stored_exception[2])
sys.exit()
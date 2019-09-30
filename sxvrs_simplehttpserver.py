#!/usr/bin/env python

"""     This is SimpleHTTPServer for showing snapshots (embedded into HASS)
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
import http.server
import html
import io
import socketserver
import urllib.parse
import mimetypes

# Global variables
vr_list = []
# Get running script name
script_path, script_name = os.path.split(os.path.splitext(__file__)[0])
app_label = script_name + f'_{datetime.now():%H%M}'
stored_exception=None

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

# Class for VR
class vr_class():
    def __init__(self, name):
        self.name = name
        self.status = 'None'
        self.error_cnt = 0 
        self.latest_file = ''
        self.snapshot = ''

# MQTT event listener
def on_mqtt_message(client, userdata, message):
    """Provides reaction on all events received from MQTT broker"""
    global vr_list
    try:
        if len(message.payload)>0:
            logger.debug("MQTT received " + str(message.payload.decode("utf-8")))
            logger.debug("MQTT topic=" + message.topic)
            logger.debug("MQTT qos=" + str(message.qos))
            logger.debug("MQTT retain flag=" + str(message.retain))
            payload = json.loads(str(message.payload.decode("utf-8")))
            if message.topic.endswith("/list"):
                logger.debug(f"receive list: {payload}")
                vr_list = []
                for name in payload:
                    vr_list.append(vr_class(name))
                    mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name=name), json.dumps({'cmd':'status'}))
                    logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name=name)} {{'cmd':'status'}}")
            else:
                for vr in vr_list:
                    if message.topic.endswith("/"+vr.name):
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
    #for vr in vr_list:
        
def on_mqtt_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT: {cnfg['mqtt']['server_ip']} rc={str(rc)}")
    mqtt_client.subscribe(cnfg['mqtt']['topic_subscribe'].format(source_name='#'))  
    logger.debug(f"MQTT subscribe: {cnfg['mqtt']['topic_subscribe'].format(source_name='#')}")
    time.sleep(1)
    mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name='list'))
    logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name='list')}")

# setup MQTT connection
try:
    mqtt_client = mqtt.Client(cnfg['mqtt']['name']) #create new instance
    mqtt_client.enable_logger(logger)
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message #attach function to callback
    mqtt_client.connect(cnfg['mqtt']['server_ip']) #connect to broker
    mqtt_client.loop_start() #start the loop
except :
    logger.exception(f"Can't connect to MQTT broker at address: {cnfg['mqtt']['server_ip']}")
    stored_exception=sys.exc_info()    

# SimpleHTTPServer implementation
class Handler(http.server.SimpleHTTPRequestHandler):
    ext_img = ['.jpeg','jpg','png','gif']
    ext_static = ['.css']

    def valid_extension(self, valid_ext_list, filename):
        """ Function checks if specified filename has valid extension """
        result = False
        for ext in valid_ext_list:
            if filename.endswith(ext):
                result = True
                break
        return result

    def do_GET(self):
        res = False
        logger.debug(f'HTTP do_GET: {self.path}')
        parsed_path = self.path.split('/')
        try:
            if len(parsed_path)==3:
                if parsed_path[1]=='static':
                    self.send_file(os.path.join('templates', 'static', parsed_path[2]))
            for vr in vr_list:
                if parsed_path[1]==vr.name:
                    if len(parsed_path)==3:
                        if parsed_path[2]=='snapshot':
                            if self.valid_extension(self.ext_img, vr.snapshot):
                                self.send_file(vr.snapshot)
                        if parsed_path[2]=='Start':
                            payload = json.dumps({'cmd':'start'})
                            mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name=vr.name), payload)
                            logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name=vr.name)} [{payload}]")
                            self.send_response(303)
                            self.send_header('Location', '/' + vr.name)
                            self.end_headers()
                        if parsed_path[2]=='Stop':
                            payload = json.dumps({'cmd':'stop'})
                            mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name=vr.name), payload)
                            logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name=vr.name)} [{payload}]")
                            self.send_response(303)
                            self.send_header('Location', '/' + vr.name)
                            self.end_headers()
                    else:
                        res = self.send_itempage(vr)
        except:
            self.send_response(501)
        #if not res:
        #    self.send_head()
    
    def send_headers(self, response, content_type, content_size):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', content_size)
        self.end_headers()

    def get_file(self, filename):
        if self.valid_extension(self.ext_img, filename):
            with open(filename, mode='rb') as f:
                content = f.read()
            return content
        else:
            with open(filename, mode='r', encoding='utf-8') as f:
                content = f.read()
            return bytes(content, 'utf-8')

    def send_file(self, filename):
        self.send_headers(200, mimetypes.guess_type(filename)[0], os.path.getsize(filename))
        self.wfile.write(self.get_file(filename))

    def load_template(self, name):
        try:
            filename = os.path.join('templates',name)
            file = open(filename, 'r')
            data = file.read()
        except:
            logger.exception(f"Can't load template file: {filename}")
        return data

    def send_itempage(self, vr):
        """Returns page for given camera"""
        enc = sys.getfilesystemencoding()
        title = f'Camera: {vr.name}'
        tmpl = self.load_template('itempage.html')
        widget = self.load_template('widget.html')
        if (not tmpl) or (not widget):
            self.send_response(501)
            return False
        else:
            blink = ''
            if vr.status == 'stopped':
                btn_name = 'Start'
                state_img = ''
            else:
                btn_name = 'Stop'
                if vr.status == 'started':
                    blink = 'blink'
                    state_img = 'rec.png'
                    widget_status = 'widget_status_ok'
                elif vr.status in ['snapshot','restarting']:
                    state_img = 'state.gif'
                    widget_status = 'widget_status'
                elif vr.status == 'error':
                    state_img = 'err.gif'
                    widget_status = 'widget_status_err'
            if vr.error_cnt>0:
                widget_err = 'widget_err' 
            else:
                widget_err = ''
            widget = widget.format(
                snapshot = vr.snapshot,
                latest_file = vr.latest_file,
                error_cnt = vr.error_cnt,
                status = vr.status,
                name = vr.name,
                btn_name = btn_name,
                blink = blink,
                state_img = state_img,
                widget_status = widget_status,
                widget_err = widget_err
            )
            html = tmpl.format(
                charset = enc,
                title = title,
                widget = widget
            )
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=%s" % enc)
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(bytes(html, enc))
            return True
    
    def list_directory(self, path):
        ''' Overwriting SimpleHTTPRequestHandler.list_directory()
                insead listing all recording instances
        '''
        enc = sys.getfilesystemencoding()
        title = 'List of all available cameras'
        tmpl = self.load_template('index.html')
        if not tmpl:
            self.send_response(501)
            return False
        else:
            html_list = ''
            for vr in vr_list:
                html_list += f'<li><a href="{vr.name}">{vr.name}</a></li>'
            html = tmpl.format(
                charset = enc,
                title = title,
                list = html_list
            )
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=%s" % enc)
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(bytes(html, enc))
            return True
    

if stored_exception==None:
    server_host = cnfg['server']['host']
    if server_host=='' or server_host is None:
        server_host = '0.0.0.0'
    logger.info(f"! HTTP server start on http://{server_host}:{cnfg['server']['port']} Press [CTRL+C] to exit")
    httpd = socketserver.TCPServer((server_host, cnfg['server']['port']), Handler)
    httpd.serve_forever()
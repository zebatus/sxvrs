#!/usr/bin/env python

"""     This is SimpleHTTPServer for showing snapshots (embedded into HASS)
Dependencies:
    pip install pyyaml paho-mqtt
    sudo apt install imagemagick 
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
import subprocess

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
                    if message.topic.lower().endswith("/"+vr.name.lower()):
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
        logger.info(f"Connected to MQTT: {cnfg['mqtt']['server_ip']} rc={str(rc)}")
        mqtt_client.subscribe(cnfg['mqtt']['topic_subscribe'].format(source_name='#'))  
        logger.debug(f"MQTT subscribe: {cnfg['mqtt']['topic_subscribe'].format(source_name='#')}")
        time.sleep(1)
        mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name='list'))
        logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name='list')}")
    else:
        logging.error(f"MQTT connection failure with code={rc}")

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
    if cnfg['mqtt']['login']!=None: 
        mqtt_client.username_pw_set(cnfg['mqtt']['login'], cnfg['mqtt']['pwd'])
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
except :
    logger.exception(f"Can't connect to MQTT broker at address: {cnfg['mqtt']['server_ip']}")
    stored_exception=sys.exc_info()    

# SimpleHTTPServer implementation
class Handler(http.server.SimpleHTTPRequestHandler):
    ext_img = ['.jpeg','.jpg','.png','.gif']
    ext_static = ['.css']

    def valid_extension(self, valid_ext_list, filename):
        """ Function checks if specified filename has valid extension """
        result = False
        for ext in valid_ext_list:
            if filename.endswith(ext):
                result = True
                break
        return result

    def refresh_vr_status(self, vr=None):
        """This function is for running of refreshment of the status for all cam"""
        if vr is None:
            for vr in vr_list:
                mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name=vr.name), json.dumps({'cmd':'status'}))
                logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name=vr.name)} {{'cmd':'status'}}")
        else:
            mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name='list'))
            logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name='list')}")

    def get_list_param(self, list, index):
        res = None
        if len(list)>index:
            res = list[index]
        return res

    def do_GET(self):
        logger.debug(f'HTTP do_GET: {self.path}')
        parsed_path = self.path.lower().split('/')
        try:
            if self.path=='/':
                self.refresh_vr_status()
                self.send_head()
            page = self.get_list_param(parsed_path,1)
            if page=='logs':
                self.send_logspage(self.get_list_param(parsed_path,2),self.get_list_param(parsed_path,3))
            if page=='restart':
                self.restart(self.get_list_param(parsed_path,2))
            if len(parsed_path)==3:
                if page=='static':
                    self.send_file(os.path.join('templates', 'static', parsed_path[2]))
            for vr in vr_list:
                if page==vr.name.lower():
                    self.refresh_vr_status(vr)
                    if len(parsed_path)>=3:
                        if parsed_path[2]=='snapshot':
                            width = None
                            height = None
                            if len(parsed_path)==5:
                                width = parsed_path[3]
                                height = parsed_path[4]
                            if self.valid_extension(self.ext_img, vr.snapshot):
                                self.send_file(vr.snapshot, param1=width, param2=height)
                        if parsed_path[2]=='start':
                            payload = json.dumps({'cmd':'start'})
                            mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name=vr.name), payload)
                            logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name=vr.name)} [{payload}]")
                            time.sleep(2) # sleep before refresh, to give time to update data
                            self.send_response(303)
                            self.send_header('Location', '/' + vr.name)
                            self.end_headers()
                        if parsed_path[2]=='stop':
                            payload = json.dumps({'cmd':'stop'})
                            mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name=vr.name), payload)
                            logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name=vr.name)} [{payload}]")
                            time.sleep(2) # sleep before refresh, to give time to update data
                            self.send_response(303)
                            self.send_header('Location', '/' + vr.name)
                            self.end_headers()
                    else:
                        self.send_itempage(vr)
        except:
            self.send_response(501)
    
    def send_headers(self, response, content_type, content_size):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', content_size)
        self.end_headers()

    def get_file(self, filename):
        try:
            if self.valid_extension(self.ext_img, filename):
                with open(filename, mode='rb') as f:
                    content = f.read()
                return content
            else:
                with open(filename, mode='r', encoding='utf-8') as f:
                    content = f.read()
                return bytes(content, 'utf-8')
        except:
            logger.exception(f"Error on get_file({filename})")

    def send_file(self, filename, param1=None, param2=None):
        try:
            if param1!=None and param2!=None: #resize image
                widtn = int(param1)
                height = int(param2)
                new_filename = f'{filename}.{widtn}x{height}.jpg'
                cmd = f'convert {filename} -resize {widtn}x{height}\> {new_filename}'
                process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, universal_newlines=True)
                process.wait(20)
                filename = new_filename
            self.send_headers(200, mimetypes.guess_type(filename)[0], os.path.getsize(filename))
            self.wfile.write(self.get_file(filename))
        except:
            logger.exception(f"Error on send_file({filename},{param1},{param2})")

    def load_template(self, name):
        try:
            filename = os.path.join('templates',name)
            file = open(filename, 'r')
            data = file.read()
        except:
            logger.exception(f"Can't load template file: {filename}")
        return data

    def send_logspage(self, page = None, max_len = None):
        logs_path = os.path.dirname(cnfg['logger']['handlers']['info_file_handler']['filename'])
        enc = sys.getfilesystemencoding()
        title = f'Logs: {page}'
        tmpl = self.load_template('logs.html')
        list_box = ""
        for file in os.listdir(logs_path):
            if os.path.isfile(os.path.join(logs_path,file)) and file[-4:] in ['.err','.log']:
                list_box += f'<li><a href="/logs/{file}">{file}</a></li>'
        if page==None:
            log_box = "Please select logs.file"
        else:
            try:
                log_box = ""
                i = 0
                if max_len is None:
                    max_len = 500
                else:
                    max_len = int(max_len)
                with open(os.path.join(logs_path, page), mode='r', encoding='utf-8') as f:
                    for row in reversed(f.readlines()):
                        log_box += html.escape(row)
                        i += 1
                        if i>max_len:
                            break
            except:
                logger.exception(f'Error in opening logs file: {page}')
                log_box = 'Error loading log file'
        content = tmpl.format(
                charset = enc,
                title = title,
                list_box = list_box,
                log_box = log_box
            )
        self.send_headers(200, f"text/html; charset={enc}", str(len(content)))
        self.wfile.write(bytes(content, enc))

    def send_itempage(self, vr, width=800, height=600):
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
                state_img = 'stop.gif'
                widget_status = 'widget_status_ok'
            else:
                btn_name = 'Stop'
                if vr.status == 'started':
                    blink = 'blink'
                    state_img = 'rec.gif'
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
            #show log for selected vr
            logs_path = os.path.dirname(cnfg['logger']['handlers']['info_file_handler']['filename'])
            logs_file = 'sxvrs_daemon.log'
            try:
                log_box = ""
                i = 0
                with open(os.path.join(logs_path, logs_file), mode='r', encoding='utf-8') as f:
                    for row in reversed(f.readlines()):
                        if vr.name in row:
                            log_box += html.escape(row)
                            i += 1
                            if i>500:
                                break
            except:
                logger.exception(f'Error in opening logs file: {logs_file}')
                log_box = 'Error loading log file'
            widget = widget.format(
                snapshot = os.path.join(vr.snapshot, str(width), str(height)),
                width = width,
                height = height,
                latest_file = os.path.basename(vr.latest_file),
                error_cnt = vr.error_cnt,
                status = vr.status,
                name = vr.name,
                btn_name = btn_name,
                blink = blink,
                state_img = state_img,
                widget_status = widget_status,
                widget_err = widget_err
            )
            content = tmpl.format(
                charset = enc,
                title = title,
                widget = widget,
                log_box = log_box
            )
            self.send_headers(200, f"text/html; charset={enc}", str(len(content)))
            self.wfile.write(bytes(content, enc))
    
    def list_directory(self, path):
        ''' Overwriting SimpleHTTPRequestHandler.list_directory()
                insead listing all recording instances
        '''
        global vr_list
        width = 300
        height = 200
        enc = sys.getfilesystemencoding()
        title = 'SXVRS'
        tmpl = self.load_template('index.html')
        widget = self.load_template('widget.html')
        if not tmpl:
            self.send_response(501)
            return False
        else:
            html_list = ''
            for vr in vr_list:
                blink = ''
                if vr.status == 'stopped':
                    btn_name = 'Start'
                    state_img = ''
                else:
                    btn_name = 'Stop'
                    if vr.status == 'started':
                        blink = 'blink'
                        state_img = 'rec.gif'
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
                snapshot = os.path.join(vr.snapshot, str(width), str(height))
                wd = widget.format(
                snapshot = snapshot,
                width = width,
                height = height,
                latest_file = os.path.basename(vr.latest_file),
                error_cnt = vr.error_cnt,
                status = vr.status,
                name = vr.name,
                btn_name = btn_name,
                blink = blink,
                state_img = state_img,
                widget_status = widget_status,
                widget_err = widget_err
                )
                html_list += f'<div class="vr_box"><div class="vr_link"><a href="{vr.name}">{vr.name}</a></div>{wd}</div>'
            if len(vr_list)==0:
                html_list = """<h3>Oops, looks like there is no any device.</h3><br>
                This may be caused by:<br>
                <ul>
                    <li>1. sxvrs_daemon is not started yet. You just need to wait and refresh this page</li>
                    <li>2. There is no any available instance configured in sxvrs_daemon </li>
                    <li>3. sxvrs_daemon is down</li>
                    <li>4. There are some problems with MQTT server or configuration for using it</li>
                </ul>
                <br>
                Please note: This HTTP server is independent and comunicates with sxvrs_daemon only by mqtt messages
                """
            content = tmpl.format(
                charset = enc,
                title = title,
                list = html_list
            )
            self.send_headers(200, f"text/html; charset={enc}", str(len(content)))
            self.wfile.write(bytes(content, enc))

    def restart(self, name = None):
        if name == "daemon":
            self.send_file(os.path.join('templates', '', 'restart_daemon.html'))
            payload = json.dumps({'cmd':'restart'})
            mqtt_client.publish(cnfg['mqtt']['topic_publish'].format(source_name=name), payload)
            logger.debug(f"MQTT publish: {cnfg['mqtt']['topic_publish'].format(source_name=name)} [{payload}]")
        else:
            try:
                self.send_file(os.path.join('templates', '', 'restart.html'))
                httpd.server_close()
                time.sleep(1)
                args = sys.argv[:]
                exe = sys.executable
                logging.info("> "*5 + " Restarting the server " + " <"*5)
                args.insert(0, sys.executable)
                if sys.platform == 'win32':
                    args = ['"%s"' % arg for arg in args]
                os.execv(exe, args)
            except:
                logger.exception("Can't restart server")
    

if stored_exception==None:
    server_host = cnfg['server']['host']
    if server_host=='' or server_host is None:
        server_host = '0.0.0.0'
    logger.info(f"! HTTP server start on http://{server_host}:{cnfg['server']['port']} Press [CTRL+C] to exit")
    is_started = False    
    while not is_started:
        try:
            httpd = socketserver.TCPServer((server_host, cnfg['server']['port']), Handler)
            is_started = True
        except OSError as e:
            if e.errno == 98:
                logger.error(f"Port {cnfg['server']['port']} already in use. Wait 5 sec and retry..")
                time.sleep(5)
            else:
                logger.exception("Can't start HTTP Server")
                sys.exit(1)
            
    logger.info(f"HTTP Server started on port {cnfg['server']['port']}. Waiting for connections..")
    httpd.serve_forever()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
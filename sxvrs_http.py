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


import os, sys, logging
import yaml
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt
import html
import io
import socketserver
import urllib.parse
import mimetypes
import subprocess


from cls.config_reader import config_reader
from cls.misc import check_topic, Recorder

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

# Global variables
recorders = {}
def get_recorder_by_name(name):
    for recorder_name in recorders:
        if recorder_name == name:
            return recorders[recorder_name]
mqtt_topic_pub = cnfg.mqtt_topic_client_publish
mqtt_topic_sub = cnfg.mqtt_topic_client_subscribe

def mqtt_publish_recorder(recorder_name, message):
    if isinstance(message, dict):
        message = json.dumps(message)
    mqtt_client.publish(mqtt_topic_pub.format(source_name=recorder_name), message)
    logger.debug(f"MQTT publish: {mqtt_topic_pub.format(source_name=recorder_name)} {message}")

# MQTT event listener
def on_mqtt_message(client, userdata, message):
    """Provides reaction on all events received from MQTT broker"""
    global recorders, mqtt_topic_pub
    try:
        if len(message.payload)>0:
            payload = json.loads(str(message.payload.decode("utf-8")))
            # topic = list
            if check_topic(message.topic, "list"):
                logger.debug(f"receive list: {payload}")
                recorders = {}
                for name in payload:
                    recorders[name] = Recorder(name)
                    mqtt_client.publish(mqtt_topic_pub.format(source_name=name), json.dumps({'cmd':'status'}))
                    logger.debug(f"MQTT publish: {mqtt_topic_pub.format(source_name=name)} {{'cmd':'status'}}")
            # topic = <recorder_name>
            else:
                for name in recorders:
                    if check_topic(message.topic, name.lower()):
                        recorders[name].update(payload)
    except:
        logger.exception(f'Error on_mqtt_message() topic: {message.topic} msg_len={len(message.payload)}')

def on_mqtt_connect(client, userdata, flags, rc):
    client.connection_rc = rc
    if rc==0:
        client.is_connected = True
        logger.info(f"Connected to MQTT: {cnfg.mqtt_server_host}:{cnfg.mqtt_server_port} rc={str(rc)}")
        mqtt_client.subscribe(mqtt_topic_sub.format(source_name='#'))  
        logger.debug(f"MQTT subscribe: {mqtt_topic_sub.format(source_name='#')}")
        time.sleep(1)
        mqtt_client.publish(mqtt_topic_pub.format(source_name='list'))
        logger.debug(f"MQTT publish: {mqtt_topic_pub.format(source_name='list')}")
    else:
        logger.error(f"MQTT connection failure with code={rc}")

# setup MQTT connection
try:
    mqtt_client = mqtt.Client(cnfg.mqtt_name_http) #create new instance
    mqtt_client.is_connected = False
    mqtt_client.connection_rc = 3
    mqtt_client.enable_logger(logger)
    mqtt_client.on_message=on_mqtt_message #attach function to callback
    mqtt_client.on_connect=on_mqtt_connect #attach function to callback
    #try to connect to broker in a loop, until server becomes available
    logger.debug(f"host={cnfg.mqtt_server_host}, port={cnfg.mqtt_server_port}, keepalive={cnfg.mqtt_server_keepalive}")
    mqtt_client.loop_start() 
    if cnfg.mqtt_login!=None: 
        mqtt_client.username_pw_set(cnfg.mqtt_login, cnfg.mqtt_pwd)
    while mqtt_client.connection_rc==3:
        try:
            logger.info(f"Try to connect to MQTT Server..")                
            mqtt_client.connect(cnfg.mqtt_server_host, 
                port = cnfg.mqtt_server_port,
                keepalive = cnfg.mqtt_server_keepalive
                ) 
            while not mqtt_client.is_connected: # blocking code untill connection
                time.sleep(1)
        except ConnectionRefusedError:
            mqtt_client.connection_rc==3
            wait = 1
            logger.info(f"Server is offline. Wait {wait} sec before retry")
            time.sleep(wait) # if server is not available, then wait for it
except :
    logger.exception(f"Can't connect to MQTT broker at address: {cnfg.mqtt_server_host}:{cnfg.mqtt_server_port}")
    stored_exception=sys.exc_info()    


#####    Flask HTTP Server   #####
from flask import Flask, render_template, redirect, url_for, send_file
app = Flask(__name__, static_url_path='/static', static_folder='templates/static', template_folder='templates')

def refresh_recorder_status(recorder=None):
    """This function is for running of refreshment of the status for all cam"""
    if recorder is None:
        for recorder_name in recorders:
            mqtt_publish_recorder(recorder_name, {'cmd':'status'})
    else:
        mqtt_publish_recorder(None, {'cmd':'status'})
        mqtt_client.publish(mqtt_topic_pub.format(source_name='list'))
        logger.debug(f"MQTT publish: {mqtt_topic_pub.format(source_name='list')}")

def recorder_view_data(recorder, width=None, height=None):
    """ This function prepares dictionary for displaying recorder
    """
    res = {
        "name": recorder.name,
        "error_cnt": recorder.error_cnt,
        "status": recorder.status,
        "latest_file": recorder.latest_file,
        "widget_err": '_',
        "widget_status": '_',
        "widget_latest_file": '_',
        "width": width,
        "height": height
    }
    res["snapshot"] = f'/recorder/{recorder.name}/snapshot'
    if width>0 and height>0:
        res["snapshot"] = res["snapshot"] + f"/{width}/{height}"
    res['title'] = f'Camera: {recorder.name}'
    res['blink'] = ''
    if recorder.status == 'stopped':
        res['btn_name'] = 'Start'
        res['state_img'] = 'stop.gif'
        res['widget_status'] = 'widget_status_ok'
    else:
        res['btn_name'] = 'Stop'
        if recorder.status == 'started':
            res['blink'] = 'blink'
            res['state_img'] = 'rec.gif'
            res['widget_status'] = 'widget_status_ok'
        elif recorder.status in ['snapshot','restarting']:
            res['state_img'] = 'state.gif'
            res['widget_status'] = 'widget_status'
        elif recorder.status == 'error':
            res['state_img'] = 'err.gif'
            res['widget_status'] = 'widget_status_err'
    if recorder.error_cnt>0:
        res['widget_err'] = 'widget_err' 
    else:
        res['widget_err'] = ''
    res['state_img'] = '/static/' + res['state_img']
    return res

@app.route('/')
def page_index():
    refresh_recorder_status()
    recorder_dict_list = []
    for recorder_name in recorders:
        recorder_dict_list.append(recorder_view_data(recorders[recorder_name], width=400, height=300))
    content = {
        "title": "SXVRS"
    }
    return render_template('index.html', content=content, recorders = recorder_dict_list)

@app.route('/logs')
@app.route('/logs/<name>')
@app.route('/logs/<name>/<max_len>/<page>')
def page_logs(name=None, page = None, max_len = None):    
    logs_path = os.path.dirname(cnfg.data['logger']['handlers']['info_file_handler']['filename'])
    charset = sys.getfilesystemencoding()
    title = f'Logs: {page}'
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
    #render_template(os.path.join('templates', 'logs.html'),
    return render_template('logs.html',
            charset = charset, 
            title = title,
            list_box = list_box,
            log_box = log_box
        )

@app.route('/restart/<name>')
def page_restart(name):
    if name == "daemon":
        payload = json.dumps({'cmd':'restart'})
        mqtt_client.publish(mqtt_topic_pub.format(source_name=name), payload)
    elif name == "http": # try to restart self (HTTP Server script)
        try:
            httpd.server_close()
            time.sleep(1)
            args = sys.argv[:]
            exe = sys.executable
            logger.info("> "*5 + " Restarting the server " + " <"*5)
            args.insert(0, sys.executable)
            if sys.platform == 'win32':
                args = ['"%s"' % arg for arg in args]
            os.execv(exe, args)
        except:
            logger.exception("Can't restart server")
    return render_template('restart.html', name=name)

@app.route('/recorder/<recorder_name>/snapshot/<width>/<height>')
def recorder_snapshot(recorder_name, width=None, height=None):
    # get snapshot name for the recorder
    filename = cnfg.recorders[recorder_name].filename_snapshot()
    if os.path.isfile(filename):
        # resize image
        new_filename = f'{filename[:-4]}.{width}x{height}.jpg'
        cmd = f'convert {filename} -resize {width}x{height}\> {new_filename}'
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, universal_newlines=True)
        process.wait(20)
        filename = new_filename    
        return send_file(new_filename)
    else:
        return send_file('templates/static/novideo.gif')

@app.route('/recorder/<recorder_name>')
def view_recorder(recorder_name):
        """Returns page for given camera"""
        enc = sys.getfilesystemencoding()
        # get recorder by name
        recorder = get_recorder_by_name(recorder_name)
        recorder_dict = recorder_view_data(recorder, width=800, height=600)
        #show log for selected recorder
        logs_path = os.path.dirname(cnfg.data['logger']['handlers']['info_file_handler']['filename'])
        logs_file = 'sxvrs_daemon.log'
        try:
            log_box = ""
            i = 0
            with open(os.path.join(logs_path, logs_file), mode='r', encoding='utf-8') as f:
                for row in reversed(f.readlines()):
                    if recorder.name in row:
                        log_box += html.escape(row)
                        i += 1
                        if i>500:
                            break
        except:
            logger.exception(f'Error in opening logs file: {logs_file}')
            log_box = 'Error loading log file'
            content = {
                "charset" : enc,
                "title" : f"Camera: recorder_name",
                "log_box" : log_box
            }
            return render_template('recorder.html', content=content, recorder=recorder_dict)



@app.route('/recorder/<recorder_name>/Start')
@app.route('/recorder/<recorder_name>/start')
def recorder_start(recorder_name):
    mqtt_client.publish(mqtt_topic_pub.format(source_name=recorder_name), json.dumps({'cmd':'start'}))
    time.sleep(2) # sleep before refresh, to give time to update data
    redirect(url_for(view_recorder))

@app.route('/recorder/<recorder_name>/Stop')
@app.route('/recorder/<recorder_name>/stop')
def recorder_stop(recorder_name):
    mqtt_client.publish(mqtt_topic_pub.format(source_name=recorder_name), json.dumps({'cmd':'stop'}))
    time.sleep(2) # sleep before refresh, to give time to update data
    redirect(url_for(view_recorder))

if stored_exception==None:
    # start HTTP Server
    logger.info(f"Starting HTTP Server on http://{cnfg.http_server_host}:{cnfg.http_server_port} Press [CTRL+C] to exit")
    is_started = False    
    while not is_started:
        try:
            #app.run(
            #        host = cnfg.http_server_host, 
            #        port = cnfg.http_server_port, 
            #        #debug = True
            #    )
            from gevent.pywsgi import WSGIServer
            http_server = WSGIServer((cnfg.http_server_host, cnfg.http_server_port), app)
            http_server.serve_forever()       
            is_started = True
        except OSError as e:
            if e.errno == 98:
                logger.error(f"Port {cnfg.http_server_host}:{cnfg.http_server_port} already in use. Wait 5 sec and retry..")
                time.sleep(5)
            else:
                logger.exception("Can't start HTTP Server")
                sys.exit(1)
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
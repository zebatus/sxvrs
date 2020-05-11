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
import gevent
import glob


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
    if client.is_connected:
        return
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
from flask import Flask, render_template, redirect, url_for, send_file, session, make_response
import cv2, math

app = Flask(__name__, static_url_path='/static', static_folder='templates/static', template_folder='templates')

def refresh_recorder_status(recorder=None):
    """This function is for running of refreshment of the status for all cam"""
    if len(recorders)==0:
        mqtt_client.publish(mqtt_topic_pub.format(source_name='list'))
        logger.debug(f"MQTT publish: {mqtt_topic_pub.format(source_name='list')}")        
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
        "refresh_img_speed": cnfg.http_refresh_img_speed * 1000,
        "name": recorder.name,
        "error_cnt": recorder.error_cnt,
        "status": recorder.status,
        "watcher": recorder.watcher,
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
    snapshot_path = os.path.dirname(os.path.abspath(cnfg.recorders[recorder.name].filename_snapshot()))
    snapshot_file = os.path.join(snapshot_path, 'snapshot.jpg')
    if os.path.isfile(snapshot_file):
        last_modified_date = datetime.fromtimestamp(os.path.getmtime(snapshot_file))
        res["snapshot"] = res["snapshot"] + f"?{last_modified_date}"
    res['title'] = f'Camera: {recorder.name}'
    res['blink'] = ''
    if recorder.status == 'stopped':
        res['btn_rec_name'] = 'Start Recording'
        res['btn_rec_cmd'] = 'start'
        res['btn_rec_img'] = 'stop.gif'
        res['widget_status'] = 'widget_status_ok'
    else:
        res['btn_rec_name'] = 'Stop Recording'
        res['btn_rec_cmd'] = 'stop'
        if recorder.status == 'started':
            res['blink'] = 'blink'
            res['btn_rec_img'] = 'rec.gif'
            res['widget_status'] = 'widget_status_ok'
        elif recorder.status in ['snapshot','restarting']:
            res['btn_rec_img'] = 'state.gif'
            res['widget_status'] = 'widget_status'
        elif recorder.status in ['error'] :
            res['btn_rec_img'] = 'err.gif'
            res['widget_status'] = 'widget_status_err'
        elif recorder.status in ['inactive','None'] :
            res['btn_rec_img'] = 'nointernet.png'
            res['widget_status'] = 'widget_status_err'
    if recorder.error_cnt>0:
        res['widget_err'] = 'widget_err' 
    else:
        res['widget_err'] = ''
    res['btn_rec_img'] = '/static/' + res['btn_rec_img']
    return res

@app.route('/')
def page_index():
    refresh_recorder_status()
    recorder_dict_list = []
    for recorder_name in recorders:
        recorder_dict_list.append(recorder_view_data(recorders[recorder_name], width=400, height=300))
    content = {
        "title": "SXVRS",
        "refresh_img_speed": cnfg.http_refresh_img_speed * 1000,
    }
    return render_template('index.html', content=content, recorders = recorder_dict_list)

@app.route('/logs')
@app.route('/logs/<name>')
@app.route('/logs/<name>/<max_len>/<page>')
def page_logs(name=None, page = None, max_len = None):    
    logs_path = os.path.dirname(cnfg.data['logger']['handlers']['info_file_handler']['filename'])
    charset = sys.getfilesystemencoding()
    title = f'Logs: {name}'
    file_list = []
    for file in os.listdir(logs_path):
        if os.path.isfile(os.path.join(logs_path,file)) and file[-4:] in ['.err','.log']:
            file_list.append(file)
    log_box = None
    if not name is None:
        try:
            log_box = ""
            i = 0
            if max_len is None:
                max_len = 500
            else:
                max_len = int(max_len)
            with open(os.path.join(logs_path, name), mode='r', encoding='utf-8') as f:
                for row in reversed(f.readlines()):
                    log_box += row
                    i += 1
                    if i>max_len:
                        break
        except:
            logger.exception(f'Error in opening logs file: {name}')
    return render_template('logs.html',
            charset = charset, 
            title = title,
            log_filename = name,
            log_box = log_box,
            file_list = file_list
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
@app.route('/recorder/<recorder_name>/snapshot/<width>/<height>/<selected_name>')
def recorder_snapshot(recorder_name, width=None, height=None, selected_name=None):
    """Returns snapshot image file"""
    recorder = get_recorder_by_name(recorder_name)
    # get snapshot name for the recorder
    if selected_name is None:
        filename = cnfg.recorders[recorder_name].filename_snapshot()
    else:
        snapshot_path = os.path.dirname(os.path.abspath(cnfg.recorders[recorder_name].filename_snapshot()))
        filename = os.path.join(snapshot_path, selected_name+'.jpg')
    if os.path.isfile(filename):
        height = int(height)
        width = int(width)
        img = cv2.imread(filename)
        # resize image and preserve aspect ratio
        orig_height, orig_width, _ = img.shape
        if orig_height > height:
            scale_height = height / orig_height
        else:
            scale_height = 1
        if orig_width > width:
            scale_width = width / orig_width
        else:
            scale_width = 1
        scale = min(scale_height, scale_width) 
        if scale < 1:
            height = math.floor(orig_height*scale)
            width = math.floor(orig_width*scale)
            img = cv2.resize(img, (width, height))               
        # encode to jpeg image
        _, img_jpg = cv2.imencode('.jpg', img)
        response = make_response(img_jpg.tostring())
        response.headers.set('Content-Type', 'image/jpeg')
        return response
    else:
        return send_file('templates/static/nosnapshot.gif')

@app.route('/recorder/<recorder_name>')
def view_recorder(recorder_name):
    """Returns page for given camera"""
    enc = sys.getfilesystemencoding()
    # get recorder by name
    recorder = get_recorder_by_name(recorder_name)
    recorder_dict = recorder_view_data(recorder, width=800, height=600)
    content = {
        "charset" : enc,
        "title" : f"Camera: {recorder_name}",
        "recorder_name": recorder_name,
    }
    return render_template('recorder.html', content=content, recorder=recorder_dict)

@app.route('/recorder/<recorder_name>/view_widget')
def view_recorder_widget(recorder_name):
    """Function will return view for recorder widget"""
    enc = sys.getfilesystemencoding()
    # get recorder by name
    recorder = get_recorder_by_name(recorder_name)
    recorder_dict = recorder_view_data(recorder, width=800, height=600)
    content = {
        "charset" : enc,
        "title" : f"Camera: {recorder_name}",
        "recorder_name": recorder_name,
    }
    return render_template('view_widget.html', content=content, recorder=recorder_dict)

@app.route('/recorder/<recorder_name>/view_snapshots')
def view_recorder_snapshots(recorder_name):
    """Function will return view with list of snapshots for given recorder"""
    # list all jpg files in snapshot folder
    snapshot_path = os.path.dirname(os.path.abspath(cnfg.recorders[recorder_name].filename_snapshot()))
    files = [f for f in glob.glob(snapshot_path + "/*.jpg", recursive=False)]
    files.sort(key=os.path.getmtime, reverse=True)
    snapshot_files = []
    if len(files)>1:
        for file in files:
            last_modified_date = datetime.fromtimestamp(os.path.getmtime(file))
            snapshot_files.append({
                "name": os.path.basename(os.path.splitext(file)[0]),
                "dt": last_modified_date
                })
    recorder = {
        'name': recorder_name,
        'snapshot_files': snapshot_files
    }
    return render_template('view_snapshots.html', recorder=recorder)

@app.route('/recorder/<recorder_name>/view_log')
@app.route('/recorder/<recorder_name>/view_log/<log_name>')
@app.route('/recorder/<recorder_name>/view_log/<log_name>/<log_len>')
@app.route('/recorder/<recorder_name>/view_log/<log_name>/<log_len>/<log_start>')
def view_recorder_log(recorder_name, log_name='daemon', log_len=500, log_start=0):
    """Function will return logs text for given recorder"""
    log_filter = ''
    if log_name=='daemon':
        log_file = f'{log_name}.log'
        log_filter = recorder_name
    elif log_name=='recorder':
        log_file = f'{log_name}_{recorder_name}.log'
    else:
        return
    #show log for selected recorder
    logs_path = os.path.dirname(os.path.abspath(cnfg.data['logger']['handlers']['info_file_handler']['filename']))
    try:
        log_data = ""
        i = 0
        with open(os.path.join(logs_path, log_file), mode='r', encoding='utf-8') as f:
            for row in reversed(f.readlines()):
                is_filtered = (log_filter == '')or(log_filter in row)
                if is_filtered and i >= log_start:
                    log_data += row #html.escape(row)
                    i += 1
                    if i > log_start + log_len:
                        break
    except:
        logger.exception(f'Error in opening logs file: {log_file}')
        log_data = f'Error loading log file: {log_file}'
    return render_template('view_log.html', log_data=log_data)

@app.route('/recorder/<recorder_name>/record/start')
def recorder_start(recorder_name):
    mqtt_client.publish(mqtt_topic_pub.format(source_name=recorder_name), json.dumps({'cmd':'start'}))
    time.sleep(2) # sleep before refresh, to give time to update data
    return redirect(url_for('view_recorder', recorder_name=recorder_name))

@app.route('/recorder/<recorder_name>/record/stop')
def recorder_stop(recorder_name):
    mqtt_client.publish(mqtt_topic_pub.format(source_name=recorder_name), json.dumps({'cmd':'stop'}))
    time.sleep(2) # sleep before refresh, to give time to update data
    return redirect(url_for("view_recorder", recorder_name=recorder_name))

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
        except KeyboardInterrupt as e:
            logger.debug("KeyboardInterrupt for HTTP server")
            sys.exit(0)
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
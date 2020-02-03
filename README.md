# sxvrs
Simple eXtendable Video Recording Script

sxvrs_daemon.py - is the main script that must run in background. It provide all recording functions

run:
    env/bin/python sxvrs_daemon.py

Available mqtt messages:
sxvrs/daemon/list
    - will return the list of the running instances

sxvrs/daemon/daemon {cmd:restart}
    - will restart script (can be used on updates)

sxvrs/daemon/[instance] {cmd:start}
    - start recording if it is not started yet

sxvrs/daemon/[instance] {cmd:stop}
    - stop recording

sxvrs/daemon/[instance] {cmd:status}
    - returns complete informations about current status of the [instance]

******************************************************************************************
sxvrs_simplehttpserver.py - This script is needed only when you whant to view your cameras 
from web browser. Actually it was created only for using inside HomeAssistant

run:    
    env/bin/python sxvrs_simplehttpserver.py


Available pages:

http://localhost:8282/logs/logfilename/max_len
    - this page show the last [max_len] rows from the [lofilename]

http://localhost:8282/restart
    - this link restarts HTTPS server itself (can be used on updates)

http://localhost:8282/restart/daemon
    - this link sends MQTT message {cmd:restart} to sxvrs_daemon script

http://localhost:8282/static/[filename]
    - it is possible to provide files located in folder: /templates/static/*
    currently supported extensions are: 'jpeg','jpg','png','gif', 'css'

http://localhost:8282/[instance]/snapshot/[width]/[height]
    - this link provides snapshot from the camera.
    if [width] and [height] parameters are provided, the image will be resized to that size

http://localhost:8282/[instance]/start
    - this link sends MQTT message {cmd:start} to sxvrs_daemon script
    This will start recording on camera

http://localhost:8282/[instance]/stop
    - this link sends MQTT message {cmd:stop} to sxvrs_daemon script
    This will stop recording on camera

How to test MQQT messages:
    Testing from linux shell:
        mosquitto_pub -m "{\"cmd\":\"start\"}" -t "sxvrs/daemon/camera_1"
        mosquitto_pub -m "{'cmd':'stop'}" -t "sxvrs/daemon/camera_1"
        mosquitto_pub -m "{'cmd':'restart'}" -t "sxvrs/daemon/daemon"


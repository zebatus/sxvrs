# SxVRS - Simple eXtendable Video Recording Script

The main purpose of this application is to record rtsp stream from ip camera into a local file with goal to be as lightweight as possible, with providing high customization capabilities via YAML config file.

Application can do:
- Keeps and maintains available disk space. 
- Creates snapshots from video source
- Run motion detection
- Run object detection
- Send messages to mqtt broker
- Implemented simple GUI via flask web server
Each recording runs in separate thread, communications between threads are done by Mosquitto MQTT Server.

To run this script you will need:
- ffmpeg (or any other application that can record rtsp streams like openrtsp, vlc)
- convert utility from imagemagick
- Mosquitto MQTT Server running on local network


## sxvrs_daemon.py
This is the main script that must run in background. It provide all recording functions

run: `env/bin/python sxvrs_daemon.py`

Available mqtt messages:
  * sxvrs/daemon/list
    - will return the list of the running instances

  * sxvrs/daemon/daemon {cmd:restart}
    - will restart script (can be used on updates)

  * sxvrs/daemon/[name] {cmd:start}
    - start recording if it is not started yet

  * sxvrs/daemon/[name] {cmd:stop}
    - stop recording

  * sxvrs/daemon/[name] {cmd:status}
    - returns complete informations about current status of the [instance]

******************************************************************************************
## sxvrs_http.py
This script is needed only when you whant to view your cameras from web browser. Actually it was created only for using inside HomeAssistant

run:`env/bin/python sxvrs_http.py`


Available pages:

  * http://localhost:8282/logs/[logfilename]/[max_len]
    - this page show the last [max_len] rows from the [lofilename]

  * http://localhost:8282/restart/http
    - this link restarts HTTPS server itself (can be used on updates)

  * http://localhost:8282/restart/daemon
    - this link sends MQTT message {cmd:restart} to sxvrs_daemon script

  * http://localhost:8282/static/[filename]
    - it is possible to provide files located in folder: /templates/static/* 

  * http://localhost:8282/recorder/[name]/snapshot/[width]/[height]
    - this link provides snapshot from the camera.
    if [width] and [height] parameters are provided, the image will be resized to that size

  * http://localhost:8282/recorder/[name]/start
    - this link sends MQTT message {cmd:start} to sxvrs_daemon script
    This will start recording on camera

  * http://localhost:8282/recorder/[name]/stop
    - this link sends MQTT message {cmd:stop} to sxvrs_daemon script
    This will stop recording on camera

### How to test MQQT messages:
For testing in linux shell, there can be used mosquitto_pub application:
```
    mosquitto_pub -m "{'cmd':'start'}" -t "sxvrs/daemon/camera_1"
    mosquitto_pub -m "{'cmd':'stop'}" -t "sxvrs/daemon/camera_1"
    mosquitto_pub -m "{'cmd':'restart'}" -t "sxvrs/daemon/daemon"
```


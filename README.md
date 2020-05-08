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


  * http://localhost:8282/logs/<name>/<max_len>/<page>
    - this page show the last <max_len> rows from the <log_name> file. <page> parameter can be used in pagination

  * http://localhost:8282/restart/http
    - this link restarts HTTPS server itself (can be used on updates)

  * http://localhost:8282/restart/daemon
    - this link sends MQTT message {cmd:restart} to sxvrs_daemon script

  * http://localhost:8282/static/<filename>
    - it is possible to provide files located in folder: /templates/static/* 

  * http://localhost:8282/recorder/<recorder_name>
    Displays the page for <recorder_name> camera. Show all snapshots and logs

  * http://localhost:8282/recorder/<name>/snapshot/<width>/<height>/<selected_name>'
    - this link provides snapshot from the camera.
    if <width> and <height> parameters are provided, the image will be resized to that size. <selected_name> is optional, and can be used to give alternative snapshot name (i.e. last_motion_snapshot)

  * http://localhost:8282/recorder/<name>/record/start
    - this link sends MQTT message {cmd:start} to sxvrs_daemon script
    This will start recording on camera

  * http://localhost:8282/recorder/<name>/record/stop
    - this link sends MQTT message {cmd:stop} to sxvrs_daemon script
    This will stop recording on camera


Views are used for AJAX load elements

  * http://localhost:8282/recorder/<recorder_name>/view_log/<log_name>/<log_len>/<log_start>
    Function returns logs text for given <recorder_name>
    Following parameters are optional: <log_name>/<log_len>/<log_start>

  * http://localhost:8282/recorder/<recorder_name>/view_snapshots
    Function returns view with list of snapshots for given recorder

### How to test MQQT messages:
For testing in linux shell, there can be used mosquitto_pub application:
```
    mosquitto_pub -m "{'cmd':'status'}" -t "sxvrs/daemon/camera_1"
    mosquitto_pub -m "{'cmd':'start'}" -t "sxvrs/daemon/camera_1"
    mosquitto_pub -m "{'cmd':'stop'}" -t "sxvrs/daemon/camera_1"
    mosquitto_pub -m "{'cmd':'watcher_start'}" -t "sxvrs/daemon/camera_1"
    mosquitto_pub -m "{'cmd':'watcher_stop'}" -t "sxvrs/daemon/camera_1"
    mosquitto_pub -m "{'cmd':'restart'}" -t "sxvrs/daemon/daemon"
```


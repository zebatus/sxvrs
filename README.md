# SxVRS - Simple eXtendable Video Recording Script

The main purpose of this application is to record rtsp stream from ip camera into a local file with goal to be as lightweight as possible, with providing high customization capabilities via YAML config file.

Application can do:
- Record video files
- Keeps and maintains available disk space. 
- Creates snapshots from video source
- Run motion detection
- Run object detection
- Send email on object detection
- Communicate via mqtt messages
- Implemented simple GUI via flask web server
Each recording runs in separate thread, communications between threads are done by Mosquitto MQTT Server.

![Preview](https://drive.google.com/uc?export=view&id=1NlwDKhZ4arfTd3VfHma0Y7nmXcAgi5YP)

To run this script you will need:
- python 3.6 or higher
- ffmpeg (or any other application that can record rtsp streams like openrtsp, vlc)
- Mosquitto MQTT Server running on local network

Please refer to:
1. [Installation-and-first-startup](https://github.com/zebatus/sxvrs/wiki/1.-Installation-and-first-startup)
2. [Introduction-in-first-setup](https://github.com/zebatus/sxvrs/wiki/2.-Introduction-in-first-setup)

## sxvrs_daemon.py
This is the main script that must run in background. It provide all recording functions

run: `env/bin/python sxvrs_daemon.py`

For available mqtt messages please refer to: [Mqtt-Messages](https://github.com/zebatus/sxvrs/wiki/4.-Mqtt-Messages)



******************************************************************************************
## sxvrs_http.py
This script is needed only when you want to view your cameras from web browser. Actually it was created only for using inside HomeAssistant

run:`env/bin/python sxvrs_http.py`


For available http pages and commands, please refer to: [Http-web-server](https://github.com/zebatus/sxvrs/wiki/6.-Http-web-server)

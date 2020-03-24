FROM python:3.7-slim
WORKDIR /opt/sxvrs
RUN mkdir -p logs
RUN mkdir -p storage
RUN mkdir cnfg
#COPY cnfg cnfg
RUN mkdir misc
COPY misc/default_config.yaml misc/default_config.yaml
COPY misc/kill.sh misc/kill.sh
COPY cls cls
COPY templates templates
COPY README.md README.md
COPY sxvrs_daemon.py sxvrs_daemon.py
COPY sxvrs_http.py sxvrs_http.py
COPY sxvrs_recorder.py sxvrs_recorder.py
COPY sxvrs_thread.py sxvrs_thread.py
COPY sxvrs_watcher.py sxvrs_watcher.py
COPY requirements.txt requirements.txt
RUN apt-get update
RUN apt-get install -y ffmpeg
RUN pip install -r requirements.txt
# Make port 8282 available to the world outside this container
EXPOSE 8282
CMD [ "python", "./sxvrs_daemon.py" ]
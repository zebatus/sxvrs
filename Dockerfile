FROM python:3.7-slim
WORKDIR /opt/sxvrs
RUN apt-get update
RUN apt-get install -y ffmpeg
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . .
# Make port 80 available to the world outside this container
EXPOSE 8282
CMD [ "python", "./sxvrs_daemon.py" ]
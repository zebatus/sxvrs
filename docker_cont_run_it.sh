#!/bin/bash

docker container rm sxvrs

docker run -it \
  --name sxvrs \
  --shm-size=256m \
  -p 8282:8282/tcp \
  -v /opt/sxvrs/cnfg:/opt/sxvrs/cnfg \
  -v /opt/sxvrs/storage:/opt/sxvrs/storage \
  -v /opt/sxvrs/logs:/opt/sxvrs/logs \
  sxvrs:latest
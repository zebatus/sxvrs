#!/bin/bash

docker image rm bugsmart/sxvrs:alpha

docker build -t bugsmart/sxvrs:alpha .

#docker push bugsmart/sxvrs:alpha
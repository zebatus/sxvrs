#!/bin/bash
watch 'ps aux|grep -e "python sxvrs_" -e ffmpeg; nvidia-smi'

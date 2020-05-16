#!/bin/bash
cd /opt/sxvrs
source /opt/sxvrs/env/bin/activate
reset
python sxvrs_daemon.py -http

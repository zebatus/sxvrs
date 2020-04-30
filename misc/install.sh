#!/bin/bash

sudo apt-get update
sudo apt-get install -y git
sudo apt-get install -y ffmpeg
sudo apt-get install -y imagemagick

cd /opt
sudo git clone https://github.com/zebatus/sxvrs.git
cd /opt/sxvrs
python3 -m venv env
source ./env/bin/activate
pip install -r requirements.txt
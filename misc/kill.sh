#!/bin/bash
kill $(ps aux | grep "python sxvrs_" | awk '{print $2}')

kill $(ps aux | grep "ffmpeg -hide_banner -nostdin -nostats" | awk '{print $2}')
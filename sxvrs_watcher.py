#!/usr/bin/env python

"""     Simple eXtendable Watcher Script
Main features:
    1) Monitor provided RAM folder and take frame
    2) Motion Detection between taken frames
    3) Run object detection if motion detected
    4) Remember for some time all detected object
    5) Take an action on frame where object was detected (email, copy, etc..)

Usage:
    python sxvrs_watcher -n <name>
"""

__author__      = "Rustem Sharipov"
__copyright__   = "Copyright 2020"
__license__     = "GPL"
__version__     = "0.2.0"
__maintainer__  = "Rustem Sharipov"
__email__       = "zebatus@gmail.com"
__status__      = "Development"
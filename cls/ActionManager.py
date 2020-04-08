#!/usr/bin/env python

# dependency: pip install matplotlib

import os, logging
from subprocess import Popen, PIPE, STDOUT
import cv2
import shutil
import json
import cv2
import math
from datetime import datetime
import numpy as np
import matplotlib.path as mplPath
# Import smtplib for the actual sending function
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from cls.Painter import Painter

class ActionManager():
    """ If object is detected, then we need to take some actions described in config file
    """
    def __init__(self, cnfg, logger_name='None'):
        self.cnfg = cnfg
        self.painter = Painter(cnfg)
        self.logger = logging.getLogger(f"{logger_name}:ActionManager")

    def run(self, obj_detected_file=None, obj_detection_results=None):
        for action in self.cnfg.actions:
            action = self.cnfg.actions[action]
            if self.check_action(action_cnfg=action, data=obj_detection_results):
                if action.type=='painter':
                    obj_detected_file_new = obj_detected_file[:-10]+'.jpg'
                    self.act_draw_box(
                        action_cnfg=action, 
                        obj_detection_results = obj_detection_results,
                        filename_in = action.file_source(filename=obj_detected_file), 
                        filename_out = action.file_target(filename=obj_detected_file_new)
                        )
                    obj_detected_file = obj_detected_file_new
                    self.logger.info(f'draw filename:{obj_detected_file}')
                elif action.type=='log':                    
                    self.act_log(
                        obj_detection_results, 
                        action_cnfg=action
                        )
                elif action.type=='mail':                    
                    self.act_send_mail(
                        action.file_source(filename=obj_detected_file),
                        config=action
                        )
                elif action.type=='copy':                    
                    self.act_copy_file(
                        action.file_source(filename=obj_detected_file), 
                        action.file_target(name=self.cnfg.name, datetime=datetime.now())
                        )

    def check_action(self, action_cnfg, data):
        """Function will check if the returned data is "ok" and if it fits config params, will return True, to run further action"""
        if data.get("result")=="ok" and len(data.get("objects",[]))>0:        
            if action_cnfg is None:
                return True
            else:
                tobe_detected = action_cnfg.objects
                score_min = action_cnfg.score
                #score_min = 0 if score_min=='' else score_min
                area = action_cnfg.area
                found = False
                i = 0
                detected = data.get('objects')
                for obj in detected:
                    if len(tobe_detected)==0 or obj['class'] in tobe_detected:
                        found = True
                    if found and obj['score']*100 >= score_min:
                        found = True
                    # check if box points are inside detection polygon area
                    if len(area) >= 3:
                        pts = np.array(area, np.int32)
                        bbPath = mplPath.Path(pts)
                        results = bbPath.contains_points([
                            (detected[i]['box'][1], detected[i]['box'][0]), 
                            (detected[i]['box'][3], detected[i]['box'][2]),
                            (detected[i]['box'][3], detected[i]['box'][0]),
                            (detected[i]['box'][1], detected[i]['box'][2]),
                            ])
                        edge_inside = False
                        for inside in results:
                            if inside:
                                edge_inside = edge_inside or inside
                        found = found and edge_inside
                    if found:
                        break
                    i += 1
                return found
        return False

    def act_draw_box(self, action_cnfg, obj_detection_results, filename_in, filename_out):
        """Function draws boxes arround each detected objects"""
        self.painter.paint(
                action_cnfg = action_cnfg,
                obj_detection_results = obj_detection_results,
                filename_in = filename_in,
                filename_out = filename_out
            )

    def act_send_mail(self, filename, config):
        """Function will send email message with attchment of catured snapshot"""
        # Create the container (outer) email message.
        msg = MIMEMultipart()
        msg['Subject'] = config.subject
        msg['From'] =  config.mail_from
        msg['To'] = config.mail_to
        msg.preamble = 'Object Detection'        
        # TODO: convert into jpeg (maybe via actions)
        self.logger.info(f'act_send_mail filename:{filename}')
        with open(filename, 'rb') as fp:
            img = MIMEImage(fp.read())
        msg.attach(img)
        s = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        s.login(config.user, config.password)
        text = msg.as_string()
        s.sendmail(config.mail_from, [config.mail_to], text)
        s.quit()

    def act_copy_file(self, file_source, file_target):
        """Function copies the file, with forcing of creation required directories"""
        try:
            path = os.path.dirname(file_target)
            if not os.path.exists(path):
                os.makedirs(path)
            shutil.copy2(file_source, file_target)
        except:
            logging.exception('Error on file copy: {file_source} -> {file_target}')
    
    def act_log(self, data, action_cnfg):
        """Action to log object detection JSON data into file"""
        try:
            filename = action_cnfg.file_target()
            if isinstance(data, dict):
                data = json.dumps(data)
            self.logger.info(f'act_log filename:{filename}')
            with open(filename, 'a+') as fp:
                fp.write(data)
                fp.write("\n")
        except:
            logging.exception(f'Can''t log to file: {filename}')
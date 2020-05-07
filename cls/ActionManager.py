#!/usr/bin/env python

# dependency: pip install matplotlib

import os, logging
from subprocess import Popen, PIPE, STDOUT
import cv2
import shutil
import json
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
    def __init__(self, cnfg, name='None'):
        self.cnfg = cnfg
        self.name = name
        self.painter = Painter(cnfg)
        self.logger = logging.getLogger(f"{name}:ActionManager")

    def run(self, obj_detected_file=None, obj_detection_results=None):
        obj_detected_file = self.convert_bmp2jpg(obj_detected_file)
        for action in self.cnfg.actions:
            action = self.cnfg.actions[action]
            if self.check_action(action_cnfg=action, data=obj_detection_results):
                tobe_detected = action.objects
                self.logger.debug(f'action cnfg={action} data={obj_detection_results} tobe_detected={tobe_detected}')
                if action.type=='painter':
                    obj_detected_file_new = action.file_target(filename=obj_detected_file)
                    self.act_draw_box(
                        action_cnfg=action, 
                        obj_detection_results = obj_detection_results,
                        filename_in = action.file_source(filename=obj_detected_file), 
                        filename_out = obj_detected_file_new
                        )
                    obj_detected_file = obj_detected_file_new
                elif action.type=='log':                    
                    self.act_log(
                        obj_detection_results, 
                        action_cnfg=action
                        )
                elif action.type=='mail':                    
                    self.act_send_mail(
                        action.file_source(filename=obj_detected_file),
                        action_cnfg=action,
                        obj_detection_results = obj_detection_results
                        )
                elif action.type=='copy':
                    for obj in obj_detection_results.get('objects'):  
                        obj_class = obj.get('class')
                        if len(tobe_detected)==0 or obj_class in tobe_detected:     
                            if action.use_memory and not obj.get('in_memory', False):            
                                self.act_copy_file(
                                    action.file_source(filename=obj_detected_file), 
                                    action.file_target(name=self.cnfg.name, datetime=datetime.now(), object_class=obj_class)
                                    )
                elif action.type=='move':                    
                    for obj in obj_detection_results.get('objects'):  
                        obj_class = obj.get('class')
                        if len(tobe_detected)==0 or obj_class in tobe_detected:                  
                            if action.use_memory and not obj.get('in_memory', False):            
                                self.act_move_file(
                                    action.file_source(filename=obj_detected_file), 
                                    action.file_target(name=self.cnfg.name, datetime=datetime.now(), object_class=obj_class)
                                    )

    def check_action(self, action_cnfg, data):
        """Function will check if the returned data is "ok" and if it fits action_cnfg params, will return True, to run further action"""
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
                    found = found and obj['score']*100 >= score_min
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

    def convert_bmp2jpg(self, filename):
        img = cv2.imread(filename)
        filename = filename[:-10] + '.jpg'
        cv2.imwrite(filename, img)
        return filename

    def act_draw_box(self, action_cnfg, obj_detection_results, filename_in, filename_out):
        """Function draws boxes arround each detected objects"""
        self.painter.paint(
                action_cnfg = action_cnfg,
                obj_detection_results = obj_detection_results,
                filename_in = filename_in,
                filename_out = filename_out
            )

    def act_send_mail(self, filename, action_cnfg, obj_detection_results):
        """Function will send email message with attchment of catured snapshot"""
        # prepare text string, that contains all detected objects
        cnt_detected = 0
        strObjects = ''
        tobe_detected = action_cnfg.objects
        for obj in obj_detection_results.get('objects'):
            if len(tobe_detected)==0 or obj.get('class') in tobe_detected :
                if not obj.get('in_memory', False):
                    strObjects += f'detected: <b>{obj.get("class")}</b>&nbsp;({obj.get("score"):.2f})<br>'
                    cnt_detected += 1
                else:
                    strObjects += f'detected: {obj.get("class")}&nbsp;({obj.get("score"):.2f})<br>'
        if action_cnfg.use_memory and cnt_detected == 0:
            self.logger.debug(f'Email not sent, as there are no new objects')
            return
        # Create the container (outer) email message.
        msg = MIMEMultipart('related')
        msg['Subject'] = action_cnfg.subject
        msg['From'] =  action_cnfg.mail_from
        msg['To'] = action_cnfg.mail_to
        msg.preamble = 'Object Detection'
        
        msgAlternative = MIMEMultipart('alternative')
        msg.attach(msgAlternative)

        msgText = MIMEText(f'Object detected on {self.name} \n {obj_detection_results}')
        msgAlternative.attach(msgText)
        msgText = MIMEText(f'Object detected on <b>{self.name}</b><br>{strObjects}<img src="cid:image1"><br>{obj_detection_results}<i></i>', 'html')
        msgAlternative.attach(msgText)

        with open(filename, 'rb') as fp:
            msgImage = MIMEImage(fp.read())
        msgImage.add_header('Content-ID', '<image1>')          
        msg.attach(msgImage)
        try:
            s = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            s.login(action_cnfg.user, action_cnfg.password)
            s.sendmail(action_cnfg.mail_from, [action_cnfg.mail_to], msg.as_string())
            s.quit()        
            self.logger.debug('email sent')        
        except smtplib.SMTPAuthenticationError as err:
            self.logger.error(f'smtplib.SMTPAuthenticationError: ({err})')

    def act_copy_file(self, file_source, file_target):
        """Action to copies file, with forced of creation required directories"""
        try:
            path = os.path.dirname(file_target)
            if not os.path.exists(path):
                os.makedirs(path)
            shutil.copy2(file_source, file_target)
        except:
            self.logger.exception('Error on file copy: {file_source} -> {file_target}')

    def act_move_file(self, file_source, file_target):
        """Action to move file, with forced of creation required directories"""
        try:
            path = os.path.dirname(file_target)
            if not os.path.exists(path):
                os.makedirs(path)
            shutil.move(file_source, file_target)
        except:
            self.logger.exception('Error on file move: {file_source} -> {file_target}')

    def act_log(self, data, action_cnfg):
        """Action to log object detection JSON data into file"""
        try:
            filename = action_cnfg.file_target()
            if isinstance(data, dict):
                data = json.dumps(data)
            with open(filename, 'a+') as fp:
                fp.write(data)
                fp.write("\n")
        except:
            self.logger.exception(f'Can''t log to file: {filename}')
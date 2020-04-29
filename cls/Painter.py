#!/usr/bin/env python

import os, sys, logging
import json
import argparse
import cv2
import numpy as np

class Painter():
    def __init__(self, cnfg, logger_name='None'):
        self.logger = logging.getLogger(f"{logger_name}:Painter")
        self.cnfg = cnfg
        self.img_height = None
        self.img_width = None
        self.img_channels = None

    def drawDetectionArea(self, action_cnfg, img):
        if len(action_cnfg.area) >= 3:
            # Draw a polygon
            pts = np.array(action_cnfg.area, np.int32)
            pts = pts.reshape((-1,1,2))
            cv2.polylines(img, [pts],True,(0,255,255))

    def drawBox(self, action_cnfg, num, img, detected):
        c = 20*num
        if c>200:
            c = 200
        color = (c, c, 255)
        box = detected['box']
        class_id = detected['class']
        score = round(100*detected['score'])
        y1 = box[0] - action_cnfg.brush_size if (box[0] - action_cnfg.brush_size)>0 else box[0]
        x1 = box[1] - action_cnfg.brush_size if (box[1] - action_cnfg.brush_size)>0 else box[1]
        y2 = box[2] + action_cnfg.brush_size if (box[2] - action_cnfg.brush_size)<self.img_width else box[2]
        x2 = box[3] + action_cnfg.brush_size if (box[3] - action_cnfg.brush_size)<self.img_height else box[3]
        cv2.rectangle(img,(x1,y1),(x2,y2), color ,2)
        cv2.putText(img,f'{class_id}', (x2+3,y1), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1) 
        cv2.putText(img,f'{score}%', (x2+3,y1+16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1) 

    def paint(self, action_cnfg, obj_detection_results, filename_in, filename_out):
        """ This is the main method to call. It draws required boxes and texts on the image and saves it to file
        """
        try:
            img = cv2.imread(filename_in)
            self.img_height, self.img_width, self.img_channels = img.shape  
            self.drawDetectionArea(action_cnfg, img)  
            # Loop over all detected objects and draw boxes around them 
            i = 0
            if not isinstance(obj_detection_results, dict):
                obj_detection_results = json.loads(obj_detection_results)
            detected_objects = obj_detection_results['objects']
            for detected in detected_objects:
                self.drawBox(action_cnfg, i, img, detected)
            # save image to output file
            cv2.imwrite(filename_out+'.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, action_cnfg.jpeg_quality])
            os.rename(filename_out+'.jpg', filename_out)
        except:
            self.logger.exception(f'Painter.paint(self, {action_cnfg}, {obj_detection_results}, {filename_in}, {filename_out})')
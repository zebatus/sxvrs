#!/usr/bin/env python

import os, sys, logging, logging.config
import json
import argparse
import cv2
import numpy as np

class Painter():
    def __init__(self, cnfg):
        self.cnfg = cnfg
        self.border = cnfg.
        self.objects = cnfg.
        self.area = cnfg.
        self.jpeg_quality = cnfg.

    def drawDetectionArea(self, img):
        if len(self.area) >= 3:
            # Draw a polygon
            pts = np.array(area, np.int32)
            pts = pts.reshape((-1,1,2))
            cv2.polylines(img, [pts],True,(0,255,255))

    def drawBox(self, num, img, detected):
        c = 20*num
        if c>200:
            c = 200
        color = (c, c, 255)
        box = detected['box']
        class_id = detected['class']
        score = round(100*detected['score'])
        y1 = box[0] - border if (box[0] - border)>0 else box[0]
        x1 = box[1] - border if (box[1] - border)>0 else box[1]
        y2 = box[2] + border if (box[2] - border)<width else box[2]
        x2 = box[3] + border if (box[3] - border)<height else box[3]
        cv2.rectangle(img,(x1,y1),(x2,y2), color ,2)
        cv2.putText(img,f'{class_id}', (x2+3,y1), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1) 
        cv2.putText(img,f'{score}%', (x2+3,y1+16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1) 

    def paint(filename_in, filename_out):
        """ This is the main method to call. It draws required boxes and texts on the image and saves it to file
        """
        img = cv2.imread(input_file)
        self.height, self.width, self.channels = img.shape  
        self.drawDetectionArea(img)  
        # Loop over all detected objects and draw boxes around them 
        i = 0
        for detected in self.objects:
            self.drawBox(i, img, detected)
        # save image to output file
        cv2.imwrite(filename_out, img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])  
#!/usr/bin/env python

import os, logging
import cv2
import matplotlib.path as mplPath
import numpy as np
import math
from random import randrange
import imutils

class MotionDetector():
    """ Loads frames and compares them for motion detection
    """
    def __init__(self, cnfg, logger_name='None'):
        self.logger = logging.getLogger(f"{logger_name}:MotionDetector")
        self.cnfg = cnfg
        self.scale = None
        self.contour_min_area = None
        self.contour_max_area = None
        self.images_bg = []
        self.last_background = None
        self.cnt_frames_changed = 0     
        self.cnt_frames_static = 0

    
    def detect(self, filename):
        """ Loads image from filename and compare with a previous
        """
        is_motion_detected = False
        frame_orig = cv2.imread(filename)
        height, width, channels = frame_orig.shape
        # Calculate scale coefitient only once, in case it is not defined yet
        if self.scale is None:
            if height > self.cnfg.motion_detector_max_image_height:
                scale_height = height > self.cnfg.motion_detector_max_image_height
            else:
                scale_height = 1
            if width > self.cnfg.motion_detector_max_image_width:
                scale_width = width > self.cnfg.motion_detector_max_image_width
            else:
                scale_width = 1
            self.scale = min(scale_height, scale_width)
        # If it is required, then resize/scale the image
        if self.scale < 1:
            height = math.floor(height*self.scale)
            width = math.floor(width*self.scale)
            frame = cv2.resize(frame_orig, (width, height))
        else:
            frame = frame_orig
        # Prepare image for comparing
        img_new = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        #img_new = cv2.GaussianBlur(img_new, (self.blur_size, self.blur_size), 0)
        # remember new image for background, and delete oldest background image
        self.images_bg.append(img_new)
        while len(self.images_bg) > self.cnfg.motion_detector_bg_frame_count:
            self.images_bg.remove(self.images_bg[0])
        # if this is a first frame, then just store it
        if len(self.images_bg) < 2:
            return None
        else:            
            i = 0 if len(self.images_bg) <= 2 else randrange(len(self.images_bg)-2)
            img_prev = self.images_bg[i]
            # find difference
            img_delta = cv2.absdiff(img_prev, img_new)
            img_thresh = cv2.threshold(img_delta, self.cnfg.motion_detector_threshold, 255, cv2.THRESH_BINARY)[1]
            # if detect by countour area
            if self.cnfg.is_motion_contour_detection:
                # Calculate min/max area only for the first frame
                if self.contour_min_area is None or self.contour_max_area is None:
                    self.contour_min_area = self.define_minmax_area(self.cnfg.motion_contour_min_area, height, width)
                    self.contour_max_area = self.define_minmax_area(self.cnfg.motion_contour_max_area, height, width)
                # dilate the thresholded image to fill in holes, then find contours
                # on thresholded image
                img_thresh = cv2.dilate(img_thresh, None, iterations=1)
                contours = cv2.findContours(img_thresh.copy(), cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE)
                contours = imutils.grab_contours(contours)            
                if len(contours)>self.cnfg.motion_contour_max_count:
                    self.save_debug_img(img_new, img_prev, img_delta, img_thresh, filename = '/dev/shm/debug.jpg')
                    self.logger.debug(f"Too many counturs found: '{len(contours)} > {self.cnfg.motion_contour_max_count}'. Skipping..")
                    return None
                else:
                    self.logger.debug(f"Counturs found: '{len(contours)}'")
                # loop over all contours                            
                max_area = 0
                for contour in contours:
                    area = cv2.contourArea(contour)
                    max_area = max(max_area, area)
                is_motion_detected = max_area >= self.contour_min_area and max_area <= self.contour_max_area
            else:
                _, dev_delta = cv2.meanStdDev(img_delta)
                is_motion_detected = dev_delta > self.cnfg.detect_by_diff_threshold                       

            # if significant changes detected
            if is_motion_detected:
                # remove image from background list if it is not static
                self.background_check()
                # save image for debug
                self.save_debug_img(img_new, img_prev, img_delta, img_thresh, filename = self.cnfg.filename_debug())
                # count number of changed frames                
                self.cnt_frames_changed += 1
                self.cnt_frames_static = 0
                if self.cnfg.is_motion_contour_detection:
                    self.logger.debug(f"frames_changed= {self.cnt_frames_changed}[{self.cnfg.motion_min_frames_changes}] area= {max_area}[{self.cnfg.motion_contour_min_area}, {self.cnfg.motion_contour_max_area}]")
                else:
                    self.logger.debug(f"frames_changed= {self.cnt_frames_changed}[{self.cnfg.motion_min_frames_changes}] dev= {dev_delta}")
                is_motion_detected = (self.cnt_frames_changed >= self.cnfg.motion_min_frames_changes)
            else:
                self.cnt_frames_static += 1
                if self.cnt_frames_static >= self.cnfg.motion_max_frames_static:
                    if self.cnt_frames_changed>0:
                        print(f"Reset max frames_changed= {self.cnt_frames_changed}")
                        self.cnt_frames_changed = 0
        return is_motion_detected

    def background_check(self):
        """Check if last image for the background is static:"""
        if self.last_background is None:
            self.last_background  = self.images_bg[-1]
            return True
        #compare with last motion frame
        img_delta = cv2.absdiff(self.last_background , self.images_bg[-1])
        self.last_background  = self.images_bg[-1]
        _, dev_delta = cv2.meanStdDev(img_delta)
        discard_background = dev_delta > self.cnfg.detect_by_diff_threshold
        if discard_background:
            self.images_bg = self.images_bg[:-1]
            return False
        else:
            img_blank = np.zeros(img_delta.shape, np.uint8)
            img_blank = cv2.putText(img_blank, f'{discard_background} = {dev_delta} > {self.cnfg.detect_by_diff_threshold}', (50,50), cv2.FONT_HERSHEY_SIMPLEX,.5,(255, 0, 0) )        
            self.save_debug_img(images_bg[-1], self.last_background, img_delta, img_blank, filename = self.cnfg.filename_debug(name=f"{self.cnfg.name}_bg"))
            return True

    def define_minmax_area(self, value, height, width):
        """ if min and max area in percentage, then need to calculate actual value """
        try:
            if(str(value).endswith('%')):
                return int(float(value.strip(' %'))*height*width/100)
            else:
                return int(value.strip())
        except:
            return int(value.strip())

    def save_debug_img(self, img_new, img_prev, img_delta, img_thresh, filename=None):
        """Function needed just for debugging and tuning motion detection. It saves: comparing frames and their substraction"""        
        if filename is None:
            if not self.cnfg._filename_debug is None:
                filename = self.cnfg.filename_debug()
            else:
                return
        # create path if it is not exists
        path = os.path.dirname(filename)
        if not os.path.exists(path):
            os.makedirs(path)
        im_1 = np.concatenate((img_prev, img_new), axis=1)
        im_2 = np.concatenate((img_delta, img_thresh), axis=1)
        im_debug = np.concatenate((im_1, im_2), axis=0)
        cv2.imwrite(filename, im_debug)
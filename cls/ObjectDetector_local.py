#!/usr/bin/env python

import os, sys, logging
import numpy as np
import tensorflow as tf
import cv2
import time

from cls.ObjectDetectorBase import ObjectDetectorBase

logging.info('Loaded tensorflow version: '+ tf.__version__)

class ObjectDetector_local(ObjectDetectorBase):
    """ Object Detection using local CPU or GPU. Make sure that you have enought CPU/GPU available, otherwice use cloud detection
    """
    def __init__(self, cnfg, logger_name='None'):
        ObjectDetectorBase.__init__(self, cnfg, logger_name)
        self.labels = ['unlabeled','person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic light','fire hydrant','street sign','stop sign','parking meter','bench','bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe','hat','backpack','umbrella','shoe','eye glasses','handbag','tie','suitcase','frisbee','skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard','tennis racket','bottle','plate','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich','orange','broccoli','carrot','hot dog','pizza','donut','cake','chair','couch','potted plant','bed','mirror','dining table','window','desk','toilet','door','tv','laptop','mouse','remote','keyboard','cell phone','microwave','oven','toaster','sink','refrigerator','blender','book','clock','vase','scissors','teddy bear','hair drier','toothbrush','hair brush','banner','blanket','branch','bridge','building-other','bush','cabinet','cage','cardboard','carpet','ceiling-other','ceiling-tile','cloth','clothes','clouds','counter','cupboard','curtain','desk-stuff','dirt','door-stuff','fence','floor-marble','floor-other','floor-stone','floor-tile','floor-wood','flower','fog','food-other','fruit','furniture-other','grass','gravel','ground-other','hill','house','leaves','light','mat','metal','mirror-stuff','moss','mountain','mud','napkin','net','paper','pavement','pillow','plant-other','plastic','platform','playingfield','railing','railroad','river','road','rock','roof','rug','salad','sand','sea','shelf','sky-other','skyscraper','snow','solid-other','stairs','stone','straw','structural-other','table','tent','textile-other','towel','tree','vegetable','wall-brick','wall-concrete','wall-other','wall-panel','wall-stone','wall-tile','wall-wood','water-other','waterdrops','window-blind','window-other','wood']
        tf.config.optimizer.set_jit(True) # activate XLA, see: https://www.tensorflow.org/xla
        self.count_GPU = len(tf.config.experimental.list_physical_devices('GPU'))
        self.logger.info(f"ObjectDetector: Num GPUs Available: {self.count_GPU}")
        #self.filename_model = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + f'/models/{model}/frozen_inference_graph.pb'
        self.filename_model = self.cnfg.object_detector_local_model_filename
        if not os.path.isfile(self.filename_model):            
            self.logger.error(f'There is no model for TF: {self.filename_model}') 
        else:
            def get_frozen_graph(graph_file):
                """Read Frozen Graph file from disk."""
                with tf.gfile.GFile(graph_file, "rb") as f:
                    graph_def = tf.compat.v1.GraphDef()
                    graph_def.ParseFromString(f.read())
                return graph_def            
            trt_graph = get_frozen_graph(self.filename_model)            
            if self.cnfg.object_detector_local_gpu == 0:
                tf_config = tf.compat.v1.ConfigProto(device_count = {'GPU': 0}) # dissable GPU optimization
            else:
                tf_config = tf.compat.v1.ConfigProto()
            if self.count_GPU > 0:
                tf_config.gpu_options.allow_growth = True
            self.tf_sess = tf.compat.v1.Session(config=tf_config)
            tf.import_graph_def(trt_graph, name='')
            self.image_tensor = self.tf_sess.graph.get_tensor_by_name('image_tensor:0')
            self.detection_boxes = self.tf_sess.graph.get_tensor_by_name('detection_boxes:0')
            self.detection_scores = self.tf_sess.graph.get_tensor_by_name('detection_scores:0')
            self.detection_classes = self.tf_sess.graph.get_tensor_by_name('detection_classes:0')
            self.num_detections = self.tf_sess.graph.get_tensor_by_name('num_detections:0')   

    def load_image(self, filename):    
        if os.path.isfile(filename):
            self.logger.debug(f"ObjectDetector: open file '{filename}' ({self.frame_width}, {self.frame_height})")
            try:
                self.image = cv2.imread(filename)
                self.original_height, self.original_width, self.original_channels = self.image.shape
                return True
            except Exception as ex:
                self.logger.exception(f"Error in ObjectDetector: can't open image '{filename}' ({self.frame_width}, {self.frame_height}) \n {cmd}")
                raise ex
        else:
            self.logger.error(f"Can't find file: '{filename}'")
            raise FileNotFoundError

    def detect(self, filename):
        """ Object Detection using CPU or GPU
        """
        if self.load_image(filename):
            # Expand dimensions since the trained_model expects images to have shape: [1, None, None, 3]
            image_np_expanded = np.expand_dims(self.image, axis=0)
            # Actual detection.
            start_time = time.time()
            (boxes, scores, classes, num) = self.tf_sess.run(
                [self.detection_boxes, self.detection_scores, self.detection_classes, self.num_detections],
                feed_dict={self.image_tensor: image_np_expanded})
            #im_height, im_width,_ = self.image.shape
            scores = scores[0].tolist()
            classes = [int(x) for x in classes[0].tolist()]            
            for i in range(len(boxes)):
                # Class 1 represents human
                #if classes[i] == 1 and scores[i] > threshold:
                if scores[i] > self.threshold:
                    self.logger.debug(f'Object detected! class:{classes[i]} score:{scores[i]}')
                    box =  (int(boxes[0,i,0] * self.original_height),
                            int(boxes[0,i,1] * self.original_width),
                            int(boxes[0,i,2] * self.original_height),
                            int(boxes[0,i,3] * self.original_width))
                    result.append({
                        'box': box,
                        'score': scores[i],
                        'class': labels[classes[i]],
                        'num': int(num[0])
                    })
            result['elapsed'] = time.time() - start_time         
            self.logger.debug(f"ObjectDetector Elapsed Time:{result['elapsed']} : \n {result}", )
            #self.tf_sess.close() ! DO NOT CLOSE SESSION
            #self.detection_graph.close()        
        return result   
